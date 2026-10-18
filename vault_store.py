"""Encrypted vault storage.

Every user-visible byte (file names, notes, file contents) is encrypted with
Fernet (AES-128-CBC + HMAC-SHA256) before it touches disk.

Envelope encryption: a random data key (DEK) encrypts all items, and the DEK
itself is wrapped by a key derived from the passphrase (KEK). Changing the
passphrase only re-wraps the DEK — stored data is never re-encrypted.

The backing store is a SQLite file whose name reveals nothing. Connections
are short-lived so worker threads can use the store safely.
"""

from __future__ import annotations

import base64
import contextlib
import json
import mimetypes
import os
import sqlite3
import time
from typing import NamedTuple

from cryptography.fernet import Fernet

import vault_crypto as crypto
from file_types import classify as _classify

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), ".spc-calc")
DB_PATH = os.path.join(APP_DIR, "vault.dat")

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".yml", ".yaml", ".py", ".ini"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    meta    BLOB NOT NULL,
    data    BLOB NOT NULL
);
"""


class VaultError(Exception):
    """Base class for vault failures."""


class WrongPassphrase(VaultError):
    pass


class ItemInfo(NamedTuple):
    id: int
    created: float
    name: str
    kind: str
    mime: str
    size: int


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{num} B"


class VaultStore:
    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._dek: bytes | None = None  # decrypted data-encryption key, held in memory only

    # -- lifecycle ---------------------------------------------------------

    def exists(self) -> bool:
        return os.path.exists(self.path)

    @contextlib.contextmanager
    def _connection(self):
        """Short-lived connection: commits, closes, and releases the file lock."""
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            conn.executescript(_SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _read_meta(self, conn: sqlite3.Connection) -> dict[str, str]:
        return dict(conn.execute("SELECT key, value FROM meta"))

    def _unwrap_dek(self, password: str) -> bytes:
        """Derive the KEK from the passphrase and unwrap the DEK."""
        with self._connection() as conn:
            meta = self._read_meta(conn)
        try:
            salt = bytes.fromhex(meta["salt"])
            iterations = int(meta["iterations"])
            verifier = meta["verifier"]
            dek_wrapped = base64.urlsafe_b64decode(meta["dek_wrapped"])
        except (KeyError, ValueError) as exc:
            raise VaultError("Vault header is corrupted") from exc
        kek = crypto.derive_key(password, salt, iterations)
        if not crypto.verify_key(kek, salt, verifier):
            raise WrongPassphrase("Wrong passphrase")
        return crypto.decrypt(kek, dek_wrapped)

    def _wrap_dek(self, kek: bytes, dek: bytes, salt: bytes, iterations: int) -> dict[str, str]:
        """Build the meta row set that wraps DEK under a given KEK."""
        return {
            "salt": salt.hex(),
            "iterations": str(iterations),
            "verifier": crypto.make_verifier(kek, salt),
            "dek_wrapped": base64.urlsafe_b64encode(crypto.encrypt(kek, dek)).decode("ascii"),
        }

    def create(self, password: str, iterations: int = crypto.PBKDF2_ITERATIONS) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        salt = crypto.new_salt()
        dek = Fernet.generate_key()
        kek = crypto.derive_key(password, salt, iterations)
        with self._connection() as conn:
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES(?, ?)",
                [("fails", "0")]
                + [(k, v) for k, v in self._wrap_dek(kek, dek, salt, iterations).items()],
            )
        self._dek = dek

    def open(self, password: str) -> None:
        """Verify the passphrase and load the DEK into memory."""
        if not self.exists():
            raise VaultError("No vault exists")
        self._dek = self._unwrap_dek(password)

    def change_password(self, old_password: str, new_password: str) -> None:
        """Re-wrap the DEK under a new passphrase. Data is never re-encrypted."""
        if not self.exists():
            raise VaultError("No vault exists")
        dek = self._unwrap_dek(old_password)  # raises WrongPassphrase on bad input
        salt = crypto.new_salt()
        kek = crypto.derive_key(new_password, salt, crypto.PBKDF2_ITERATIONS)
        with self._connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                [(k, v) for k, v in self._wrap_dek(kek, dek, salt, crypto.PBKDF2_ITERATIONS).items()]
                + [("fails", "0")],
            )
        self._dek = dek

    def close(self) -> None:
        self._dek = None

    def _require_dek(self) -> bytes:
        if self._dek is None:
            raise VaultError("Vault is locked")
        return self._dek

    # -- brute-force resistance -------------------------------------------

    def get_fails(self) -> int:
        with self._connection() as conn:
            return int(self._read_meta(conn).get("fails", "0"))

    def set_fails(self, count: int) -> None:
        with self._connection() as conn:
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('fails', ?)", (str(count),))

    def wipe(self) -> None:
        """Destroy the vault file. Used after too many failed unlock attempts."""
        self._dek = None
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    # -- items -------------------------------------------------------------

    def add_text(self, name: str, text: str) -> int:
        return self._add(name, text.encode("utf-8"))

    def add_file(self, path: str) -> int:
        with open(path, "rb") as fh:
            data = fh.read()
        return self._add(os.path.basename(path), data)

    def _add(self, name: str, data: bytes) -> int:
        dek = self._require_dek()
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        meta = {
            "name": name,
            "kind": _classify(name, mime),
            "mime": mime,
            "size": len(data),
        }
        blob_meta = crypto.encrypt(dek, json.dumps(meta).encode("utf-8"))
        blob_data = crypto.encrypt(dek, data)
        with self._connection() as conn:
            cur = conn.execute(
                "INSERT INTO items(created, meta, data) VALUES(?, ?, ?)",
                (time.time(), blob_meta, blob_data),
            )
            return int(cur.lastrowid)

    def list_items(self) -> list[ItemInfo]:
        dek = self._require_dek()
        with self._connection() as conn:
            rows = conn.execute("SELECT id, created, meta FROM items ORDER BY created DESC").fetchall()
        items = []
        for item_id, created, blob_meta in rows:
            meta = json.loads(crypto.decrypt(dek, blob_meta).decode("utf-8"))
            items.append(ItemInfo(item_id, created, meta["name"], meta["kind"], meta["mime"], meta["size"]))
        return items

    def read(self, item_id: int) -> bytes:
        dek = self._require_dek()
        with self._connection() as conn:
            row = conn.execute("SELECT data FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise VaultError("Item no longer exists")
        return crypto.decrypt(dek, row[0])

    def delete(self, item_id: int) -> None:
        self._require_dek()
        with self._connection() as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))

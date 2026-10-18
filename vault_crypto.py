"""Key derivation and authenticated symmetric encryption for the vault."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# OWASP-adjacent tuning: ~0.3-0.8 s of work per guess on typical hardware.
PBKDF2_ITERATIONS = 400_000
SALT_SIZE = 16


class DecryptionError(Exception):
    """Wrong passphrase or corrupted ciphertext."""


def new_salt() -> bytes:
    return os.urandom(SALT_SIZE)


def derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """PBKDF2-HMAC-SHA256 -> url-safe Fernet key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def make_verifier(key: bytes, salt: bytes) -> str:
    """Keyed checksum so a wrong passphrase is detected without decrypting data."""
    return hmac.new(key, salt + b":verifier", hashlib.sha256).hexdigest()


def verify_key(key: bytes, salt: bytes, verifier: str) -> bool:
    return hmac.compare_digest(make_verifier(key, salt), verifier)


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    return Fernet(key).encrypt(plaintext)


def decrypt(key: bytes, token: bytes) -> bytes:
    try:
        return Fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise DecryptionError("Wrong passphrase or corrupted data") from exc

"""Headless tests for the calculator engine and encrypted vault store."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calc_engine import CalcError, evaluate, format_result, normalize, toggle_sign
from vault_store import VaultStore, WrongPassphrase, human_size
import vault_crypto as crypto


def expect_raises(expr):
    try:
        evaluate(expr)
    except CalcError:
        return
    raise AssertionError(f"{expr!r} should have raised CalcError")


# -- engine ------------------------------------------------------------------

assert evaluate("2+3*4") == 14
assert evaluate("10÷4") == 2.5
assert evaluate("(2+3)*4") == 20
assert evaluate("2^3^2") == 512          # right associative
assert evaluate("2^-1") == 0.5
assert evaluate("-5+3") == -2
assert evaluate("50%") == 0.5
assert evaluate("(-3)^2") == 9
assert evaluate("1.5×2") == 3.0
assert evaluate("6769÷6996") == 6769 / 6996

expect_raises("")
expect_raises("2^")
expect_raises("*/2")
expect_raises("((1)")
expect_raises("2..3")
expect_raises("abc")
expect_raises("9^99999")   # overflow

assert format_result(2.0) == "2"
assert format_result(0.1 + 0.2) == "0.3"
assert format_result(1 / 3) == "0.3333333333"
assert format_result(0) == "0"

assert toggle_sign("12+3") == "12+(-3)"
assert toggle_sign("12+(-3)") == "12+3"
assert toggle_sign("") == "-"
assert evaluate(toggle_sign("5")) == -5
assert evaluate("7+" + toggle_sign("5")) == 2

assert normalize("6769 ÷ 6996") == "6769/6996"
assert normalize("6769×6996") == "6769*6996"

# -- crypto ------------------------------------------------------------------

salt = crypto.new_salt()
key = crypto.derive_key("hunter2", salt)
assert crypto.verify_key(key, salt, crypto.make_verifier(key, salt))
token = crypto.encrypt(key, b"secret bytes")
assert crypto.decrypt(key, token) == b"secret bytes"
wrong = crypto.derive_key("wrong", salt)
try:
    crypto.decrypt(wrong, token)
    raise AssertionError("wrong key should not decrypt")
except crypto.DecryptionError:
    pass

# -- vault store -------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "vault.dat")
    store = VaultStore(path)

    assert not store.exists()
    store.create("correct horse")
    assert store.exists()

    store.add_text("hello.txt", "hello world")
    store.add_text("notes.md", "# heading\nbody text")
    sample = os.path.join(tmp, "sample.bin")
    with open(sample, "wb") as fh:
        fh.write(os.urandom(1024))
    store.add_file(sample)

    items = store.list_items()
    assert len(items) == 3
    by_name = {i.name: i for i in items}
    assert by_name["hello.txt"].kind == "text"
    assert by_name["sample.bin"].kind == "file"
    assert store.read(by_name["hello.txt"].id) == b"hello world"
    assert store.read(by_name["sample.bin"].id) == open(sample, "rb").read()

    # raw file on disk must contain no plaintext
    raw = open(path, "rb").read()
    assert b"hello world" not in raw
    assert b"hello.txt" not in raw
    assert b"notes.md" not in raw

    # wrong passphrase rejected
    fresh = VaultStore(path)
    try:
        fresh.open("nope")
        raise AssertionError("wrong passphrase accepted")
    except WrongPassphrase:
        pass
    fresh.set_fails(7)
    assert VaultStore(path).get_fails() == 7

    fresh.open("correct horse")
    assert fresh.get_fails() == 7
    fresh.set_fails(0)
    fresh.delete(by_name["notes.md"].id)
    assert len(fresh.list_items()) == 2
    fresh.close()

    try:
        fresh.list_items()
        raise AssertionError("locked store must reject reads")
    except Exception:
        pass

    # password change: old fails, new works, data survives
    fresh.open("correct horse")
    fresh.change_password("correct horse", "new passphrase")
    fresh.close()
    after = VaultStore(path)
    try:
        after.open("correct horse")
        raise AssertionError("old passphrase must not work after change")
    except WrongPassphrase:
        pass
    after.open("new passphrase")
    assert len(after.list_items()) == 2
    assert after.read(by_name["hello.txt"].id) == b"hello world"

    # wrong current passphrase blocks the change
    after.close()
    after.open("new passphrase")
    try:
        after.change_password("not it", "third")
        raise AssertionError("wrong current passphrase must block change")
    except WrongPassphrase:
        pass
    after.close()

    # wipe
    VaultStore(path).wipe()
    assert not os.path.exists(path)

assert human_size(512) == "512 B"
assert human_size(2048) == "2.0 KB"

print("ALL TESTS PASSED")

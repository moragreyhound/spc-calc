"""Functional UI test: drives the real widgets without a display loop.

Worker threads that call self.after() need a real mainloop, so this test
bypasses the threaded dialog paths and calls the store directly, then
verifies the UI renders and responds correctly.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vault_ui
from vault_store import VaultStore

# redirect the vault to a temp file before any UI is built
_TMP = tempfile.mkdtemp(prefix="spc-ui-test-")
_TMP_DB = os.path.join(_TMP, "vault.dat")
vault_ui.VaultStore = lambda *a, **k: VaultStore(_TMP_DB)

import app as app_mod  # noqa: E402


def pump(app, seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


app = app_mod.App()
try:
    vault = app.vault
    pump(app, 0.3)

    # -- first run: setup screen visible --
    assert vault.setup_screen.winfo_ismapped(), "setup screen should be visible on first run"

    # -- create the vault directly (bypassing threaded dialog) --
    vault.store.create("ui-test-pass")
    vault.enter()
    pump(app, 0.2)
    assert vault.main_screen.winfo_ismapped(), "browser should be visible after enter"

    # -- add items through the store, then refresh via the UI --
    vault.store.add_text("todo.txt", "buy milk\ncall mom\nship it")
    vault.store.add_text("script.py", "print('hello')\nprint('world')")
    vault.refresh_list()
    pump(app, 0.2)
    assert len(vault.items) == 2, f"expected 2 items, got {len(vault.items)}"
    assert vault.item_list.winfo_children(), "item rows should be rendered"
    assert vault.count_badge.cget("text") == "2"

    # -- select a text item: viewer should be built and filled --
    text_item = next(i for i in vault.items if i.name == "todo.txt")
    vault._select(text_item)
    pump(app, 0.2)
    assert "todo.txt" in vault.breadcrumb.cget("text")
    viewer = vault.viewer._viewer
    assert viewer is not None, "viewer should exist after selection"
    body_text = viewer._body.get("1.0", "end-1c")
    assert "buy milk" in body_text, "text viewer should show file content"
    gutter_text = viewer._gutter.get("1.0", "end-1c")
    assert "1" in gutter_text and "3" in gutter_text, "gutter should show line numbers"

    # -- add a binary item and verify the hex viewer handles it --
    bin_path = os.path.join(_TMP, "data.bin")
    with open(bin_path, "wb") as fh:
        fh.write(bytes(range(256)) * 4)
    vault.store.add_file(bin_path)
    vault.refresh_list()
    pump(app, 0.2)
    bin_item = next(i for i in vault.items if i.name == "data.bin")
    assert bin_item.kind == "file", f"unknown binary should be kind 'file', got {bin_item.kind}"
    vault._select(bin_item)
    pump(app, 0.2)
    viewer = vault.viewer._viewer
    assert viewer is not None
    body = viewer._text._textbox.get("1.0", "end-1c")
    assert "00 01" in body or "00000000" in body, \
        f"hex viewer should render hex dump, got: {body[:80]!r}"

    # -- lock, then re-enter via the secret equation on the calculator --
    vault.lock()
    pump(app, 0.2)
    assert app.calculator.winfo_ismapped(), "calculator should be visible after lock"
    assert not vault.unlocked

    for ch in "6769":
        app.press(ch)
    app.press("÷")
    for ch in "6996":
        app.press(ch)
    app.press("=")
    pump(app, 0.3)
    assert vault.lock_screen.winfo_ismapped() or vault.main_screen.winfo_ismapped(), \
        "secret equation should open the vault gate"

    # -- unlock through the real lock screen --
    if vault.lock_screen.winfo_ismapped():
        vault.lock_pass.insert(0, "ui-test-pass")
        # _attempt_unlock uses a thread; call the store directly instead
        vault.store.open("ui-test-pass")
        vault.enter()
        pump(app, 0.2)
        assert vault.unlocked
        assert vault.main_screen.winfo_ismapped()

    # -- password change through the store --
    vault.store.change_password("ui-test-pass", "rotated-pass")
    vault.lock()
    pump(app, 0.2)
    vault.store.open("rotated-pass")
    vault.enter()
    pump(app, 0.2)
    assert vault.unlocked, "new passphrase should work after rotation"

    print("UI TESTS PASSED")
finally:
    app.destroy()
    try:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    except Exception:
        pass

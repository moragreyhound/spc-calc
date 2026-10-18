# spc-calc

A plain-looking calculator with a hidden, encrypted vault behind it.

## Run

```powershell
python app.py
```

or use the portable executable: `dist\Calculator.exe` (everything bundled,
no Python install needed on the target machine).

## The secret

Enter `6769÷6996` and press `=`. The window transforms into the vault.

- First run: create a passphrase (min 6 characters). There is no recovery —
  losing it means losing the vault.
- Store notes, images, audio, video, PDFs, archives, binaries — every file
  type opens in a built-in viewer (text editor with line numbers, image
  preview, media player, hex dump).
- Change the passphrase any time from the vault's icon rail.

## Security model

- All items are encrypted with **AES-128-CBC + HMAC-SHA256** (Fernet) before
  touching disk. File names too — the raw SQLite file contains no plaintext.
- Passphrase → **PBKDF2-HMAC-SHA256, 400,000 iterations** → key-encryption
  key. Items are wrapped by a random data key, so changing the passphrase
  never re-encrypts your data.
- 5 wrong attempts → 30 s lockout. 10 wrong attempts → the vault erases itself.
- Auto-locks after 5 idle minutes.
- Vault file lives at `%APPDATA%\.spc-calc\vault.dat`.

## UI

Tokyo Night / AstroVim palette, JetBrains Mono, VS Code style file explorer,
Google Drive style preview pane. Icons are drawn in code (PIL) — no emoji,
no external assets.

## Tests

```powershell
python test_headless.py   # engine + crypto + vault store
python test_ui.py         # drives the real widgets end-to-end
```

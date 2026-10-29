# Standalone verifier (no Python, no pip)

**Product version:** 4.7.0. Related: [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md),
[RECIPIENT-CARD.md](./RECIPIENT-CARD.md), [KEY-CUSTODY.md](./KEY-CUSTODY.md).

`epi verify` is the authoritative check, but it normally needs Python 3.11+ and
`pip install epi-recorder`. That is a real cost when the person who must check
the file is an auditor, an insurer, or a counterparty with a locked-down
laptop. `verifier.spec` builds that command into a single executable.

```bash
python -m PyInstaller verifier.spec --clean --distpath dist-verifier
# -> dist-verifier/epi-verify        (Linux/macOS)
# -> dist-verifier/epi-verify.exe    (Windows)
```

Then hand over one file:

```bash
./epi-verify verify case.epi                    # human-readable report
./epi-verify verify case.epi --policy strict    # exit 1 = do not rely
./epi-verify --version                          # epi-verify 4.7.0
```

The binary is self-contained: Python, `cryptography`, `typer`, `rich` and the
inlined viewer assets are inside it. Nothing is installed and no admin rights
are needed. CI builds it on Windows, Linux and macOS
(`.github/workflows/standalone-verifier.yml`).

## What it changes, and what it does not

| | Effect |
|---|---|
| Removes | the Python/pip prerequisite on the receiving side |
| Keeps | the whole trust model: `PASS` / `WARN` / `FAIL`, pinning, `--policy strict` |
| Does not do | prove the signer's identity. An unpinned key still reports `WARN`, and `--policy strict` still `FAIL`s until you pin the sender |

Same rule as the installed CLI: **trust `epi verify`, not the colours in the
embedded viewer**.

## Signing the binary (release step)

An unsigned 80 MB executable will trip SmartScreen and some endpoint agents.
Sign it before publishing:

```powershell
# Windows
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f cert.pfx epi-verify.exe
```
```bash
# macOS
codesign --sign "Developer ID Application: …" --options runtime epi-verify
# Linux
gpg --armor --detach-sign epi-verify
```

Publish the SHA-256 alongside it so a recipient can check the download before
trusting it:

```bash
sha256sum epi-verify
```

## Known trade-offs

- **Size:** ~80 MB (onefile bundles the runtime). Use the existing `epi.spec`
  if you prefer a one-folder bundle (faster start, ~50 MB, more files to copy).
- **Startup:** onefile extracts to a temp directory on each run, ~5–9 s cold.
  Acceptable for a one-off audit; not a fit for batch verification of thousands
  of files — install the package for that.
- **Platform:** PyInstaller does not cross-compile. Build on each OS you
  support (the workflow does).

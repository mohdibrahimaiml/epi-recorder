# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for a single-file, dependency-free EPI verifier.
#
# Purpose: an auditor with no Python, no pip and no admin rights runs
#   epi-verify verify case.epi --policy strict
# from a USB stick. That is the "anyone can check this file" promise without
# asking them to install a runtime first.
#
# Build (Windows/Linux/macOS on the matching OS):
#   python -m PyInstaller verifier.spec --clean --distpath dist-verifier
#
# Output: dist-verifier/epi-verify(.exe)
#
# The resulting binary is unsigned unless you sign it afterwards (signtool,
# codesign, gpg). Signing is a release step, not a build step.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for pkg in ("epi_cli", "epi_core", "rich", "typer", "cryptography", "click", "cbor2"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["epi_cli/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "epi_cli.main",
        "epi_cli.verify",
        "epi_cli.view",
        "epi_cli.keys",
        "epi_core.container",
        "epi_core.trust",
        "epi_core.serialize",
        "epi_core.schemas",
        "epi_core.did_web",
        "epi_core.notarize",
        "epi_core.viewer_assets",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "winreg",
        "ctypes",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "numpy",
        "pandas",
        "PIL",
        "pytest",
        "playwright",
        "fastapi",
        "starlette",
        "uvicorn",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="epi-verify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="epi_core/assets/epi.ico",
)

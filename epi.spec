# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for EPI Recorder
# Produces a single-directory bundle: dist/epi/epi.exe
# Used by the Inno Setup installer (installer/windows/setup.iss)
#
# Build with:  pyinstaller epi.spec --clean
#

from PyInstaller.utils.hooks import collect_all, collect_data_files
import sys

# Collect everything from the main packages
datas = []
binaries = []
hiddenimports = []

for pkg in ("epi_cli", "epi_core", "rich", "typer", "cryptography", "click"):
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
        "epi_cli.run",
        "epi_cli.view",
        "epi_cli.ls",
        "epi_cli.verify",
        "epi_cli.record",
        "epi_cli.keys",
        "epi_cli.install",
        "epi_core.platform.associate",
        "epi_core.container",
        "epi_core.trust",
        "epi_core.redactor",
        "epi_core.serialize",
        "epi_core.storage",
        "epi_core.schemas",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "winreg",
        "ctypes",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "numpy", "pandas", "PIL"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="epi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # keep console for CLI output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="epi_core/assets/epi.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="epi",
)

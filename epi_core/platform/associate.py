"""
EPI File Association — Register .epi as an OS file type.

Double-clicking a .epi file will open `epi view <file>` automatically.
All registration uses user-level settings (no admin/root required).

    Windows:  HKEY_CURRENT_USER\\Software\\Classes (via winreg)
    macOS:    ~/Library/Application Support/EPI/EPI Viewer.app (Info.plist)
    Linux:    ~/.local/share/mime + ~/.local/share/applications (xdg-mime)

Usage:
    from epi_core.platform.associate import register_file_association
    register_file_association()           # Register .epi file type
    unregister_file_association()         # Clean removal
"""

import shutil
import subprocess
import sys
from pathlib import Path


# ============================================================
# Windows
# ============================================================

def _get_epi_command() -> str:
    """Get the correct epi command for the current Python installation."""
    import site
    
    # Common locations for epi.exe
    search_dirs = [
        Path(sys.executable).parent,          # Standard
        Path(sys.executable).parent / "Scripts", # Windows alternate
        Path(site.getuserbase()) / "Scripts",    # User-site (Windows Store Python)
        Path(site.getsitepackages()[0]) / "Scripts" if hasattr(site, 'getsitepackages') else None
    ]
    
    for scripts_dir in search_dirs:
        if scripts_dir and scripts_dir.exists():
            for candidate in ["epi.exe", "epi"]:
                exe = scripts_dir / candidate
                if exe.exists():
                    return f'"{exe}" view "%1"'
    
    # Fallback: invoke via current Python executable directly
    # Use -m to ensure the same environment is used
    return f'"{sys.executable}" -m epi_cli view "%1"'

def register_windows() -> None:
    """Register .epi file association on Windows via HKCU registry."""
    import winreg
    import ctypes

    open_cmd = _get_epi_command()

    # 1. Register .epi extension → ProgID
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Classes\.epi", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "EPIRecorder.File")
    except Exception as e:
        if not ctypes.windll.shell32.IsUserAnAdmin():
             # Fallback or silent fail if no permissions, but HKCU should work.
             pass

    # 2. Register ProgID with human-readable description
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Classes\EPIRecorder.File", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "EPI Recording File")
    except Exception:
        pass

    # 3. Register shell open command
    try:
        cmd_path = r"Software\Classes\EPIRecorder.File\shell\open\command"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, cmd_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, open_cmd)
    except Exception:
        pass

    # 4. Notify Windows shell to refresh file associations
    try:
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
        )
    except Exception:
        pass


def unregister_windows() -> None:
    """Remove .epi file association from Windows registry."""
    import winreg
    import ctypes

    def _delete_key_tree(root, path):
        """Recursively delete a registry key tree."""
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
                # Delete all subkeys first
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, 0)
                        _delete_key_tree(root, f"{path}\\{subkey_name}")
                    except OSError:
                        break
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass  # Key doesn't exist — nothing to delete

    _delete_key_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\.epi")
    _delete_key_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\EPIRecorder.File")

    # Notify shell
    SHCNE_ASSOCCHANGED = 0x08000000
    SHCNF_IDLIST = 0x0000
    ctypes.windll.shell32.SHChangeNotify(
        SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
    )


# ============================================================
# macOS
# ============================================================

def register_macos() -> None:
    """Register .epi file association on macOS via app bundle + lsregister."""
    import plistlib

    # Create a minimal .app bundle
    app_base = (
        Path.home()
        / "Library"
        / "Application Support"
        / "EPI"
        / "EPI Viewer.app"
    )
    contents = app_base / "Contents"
    macos_dir = contents / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    # Write Info.plist declaring UTI for .epi
    plist_data = {
        "CFBundleIdentifier": "com.epilabs.viewer",
        "CFBundleName": "EPI Viewer",
        "CFBundleVersion": "1.0",
        "CFBundleExecutable": "epi-open",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeExtensions": ["epi"],
                "CFBundleTypeName": "EPI Recording File",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Owner",
            }
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": "com.epilabs.epi",
                "UTTypeConformsTo": ["public.zip-archive"],
                "UTTypeTagSpecification": {
                    "public.filename-extension": ["epi"]
                },
            }
        ],
    }
    plist_path = contents / "Info.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)

    # Create launcher shell script
    exe_path = macos_dir / "epi-open"
    exe_path.write_text('#!/bin/bash\nepi view "$1"\n', encoding="utf-8")
    exe_path.chmod(0o755)

    # Register with Launch Services
    lsregister = (
        "/System/Library/Frameworks/CoreServices.framework"
        "/Versions/A/Frameworks/LaunchServices.framework"
        "/Versions/A/Support/lsregister"
    )
    if Path(lsregister).exists():
        result = subprocess.run(
            [lsregister, "-f", str(app_base)],
            capture_output=True, timeout=10
        )
        # Force LaunchServices database rebuild to avoid propagation delay
        subprocess.run(
            [lsregister, "-kill", "-r", "-domain", "local", "-domain", "user"],
            capture_output=True, timeout=15
        )
    else:
        _register_macos_osascript_fallback()

def _register_macos_osascript_fallback():
    """Fallback for macOS without lsregister (very old systems)."""
    script = '''
    tell application "Finder"
        set epiFile to POSIX file "/tmp/test.epi"
    end tell
    '''
    # Just warn — osascript registration is unreliable
    print("[WARNING] macOS: lsregister not found. Run 'epi associate' after restarting Finder.")


def unregister_macos() -> None:
    """Remove .epi file association from macOS."""
    app_base = (
        Path.home()
        / "Library"
        / "Application Support"
        / "EPI"
        / "EPI Viewer.app"
    )
    if app_base.exists():
        shutil.rmtree(app_base, ignore_errors=True)

    # Unregister from Launch Services
    lsregister = (
        "/System/Library/Frameworks/CoreServices.framework"
        "/Versions/A/Frameworks/LaunchServices.framework"
        "/Versions/A/Support/lsregister"
    )
    if Path(lsregister).exists():
        subprocess.run(
            [lsregister, "-u", str(app_base)],
            capture_output=True,
        )


# ============================================================
# Linux
# ============================================================

def register_linux() -> None:
    """Register .epi file association on Linux via xdg-mime."""
    # 1. Write MIME type definition
    mime_dir = Path.home() / ".local" / "share" / "mime" / "packages"
    mime_dir.mkdir(parents=True, exist_ok=True)
    (mime_dir / "epi-recorder.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        '  <mime-type type="application/x-epi-recording">\n'
        '    <comment>EPI Recording File</comment>\n'
        '    <glob pattern="*.epi"/>\n'
        '    <magic priority="50">\n'
        '      <match type="string" offset="0" value="PK"/>\n'
        '    </magic>\n'
        '  </mime-type>\n'
        '</mime-info>\n',
        encoding="utf-8",
    )

    # 2. Write .desktop launcher
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    (desktop_dir / "epi-viewer.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=EPI Viewer\n"
        "Exec=epi view %f\n"
        "MimeType=application/x-epi-recording;\n"
        "NoDisplay=true\n",
        encoding="utf-8",
    )

    # 3. Update MIME database and register default handler
    errors = []

    if shutil.which("update-mime-database"):
        mime_base = Path.home() / ".local" / "share" / "mime"
        r = subprocess.run(
            ["update-mime-database", str(mime_base)],
            capture_output=True, timeout=10
        )
        if r.returncode != 0:
            errors.append("update-mime-database failed")
    else:
        errors.append("update-mime-database not found (install: shared-mime-info)")

    if shutil.which("xdg-mime"):
        r = subprocess.run(
            ["xdg-mime", "default", "epi-viewer.desktop", "application/x-epi-recording"],
            capture_output=True, timeout=10
        )
        if r.returncode != 0:
            errors.append("xdg-mime default failed")
    else:
        errors.append("xdg-mime not found (install: xdg-utils)")

    if errors:
        print("[WARNING] Linux file association partially failed:")
        for e in errors:
            print(f"   - {e}")
        print("   Fix with: sudo apt install xdg-utils shared-mime-info")
        print("   Then run: epi associate")


def unregister_linux() -> None:
    """Remove .epi file association from Linux."""
    mime_xml = Path.home() / ".local" / "share" / "mime" / "packages" / "epi-recorder.xml"
    desktop_file = Path.home() / ".local" / "share" / "applications" / "epi-viewer.desktop"

    if mime_xml.exists():
        mime_xml.unlink()
    if desktop_file.exists():
        desktop_file.unlink()

    # Rebuild MIME database
    mime_base = Path.home() / ".local" / "share" / "mime"
    if mime_base.exists():
        subprocess.run(
            ["update-mime-database", str(mime_base)],
            capture_output=True,
        )


# ============================================================
# Unified Entry Points
# ============================================================

import json

_FLAG_PATH = Path.home() / ".epi" / ".filetype_registered"

def _get_registration_state() -> dict:
    try:
        return json.loads(_FLAG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _set_registration_state():
    try:
        _FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "version": _get_epi_version(),
            "executable": sys.executable,
            "platform": sys.platform
        }
        _FLAG_PATH.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass  # Harmless — just means we re-register next run

def _needs_registration() -> bool:
    """
    Check if we need to perform registration.
    Returns True if:
    1. Version/Executable has changed
    2. The actual OS association is missing or incorrect (Hardened Check)
    """
    try:
        # Check 1: Flag file state
        state = _get_registration_state()
        if (state.get("version") != _get_epi_version() or
            state.get("executable") != sys.executable):
            return True
            
        # Check 2: Actual OS state (Self-Healing)
        return _is_association_broken()
    except Exception:
        return True

def _is_association_broken() -> bool:
    """Perform real-time health check on OS file association."""
    try:
        if sys.platform == "win32":
            import winreg
            try:
                # Check .epi -> EPIRecorder.File
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.epi") as key:
                    if winreg.QueryValue(key, "") != "EPIRecorder.File":
                        return True
                
                # Check Command matches current exe
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\EPIRecorder.File\shell\open\command") as key:
                    current_cmd = _get_epi_command()
                    if winreg.QueryValue(key, "") != current_cmd:
                        return True
            except FileNotFoundError:
                return True
                
        elif sys.platform == "darwin":
            app_base = Path.home() / "Library/Application Support/EPI/EPI Viewer.app"
            if not app_base.exists():
                return True
                
        elif sys.platform.startswith("linux"):
            desktop_file = Path.home() / ".local/share/applications/epi-viewer.desktop"
            if not desktop_file.exists():
                return True
                
        return False
    except Exception:
        return True

def _get_epi_version() -> str:
    try:
        from epi_core import __version__
        return __version__
    except Exception:
        return "unknown"

def _clear_registered() -> None:
    """Remove the registration flag."""
    if _FLAG_PATH.exists():
        _FLAG_PATH.unlink()


def register_file_association(silent: bool = False, force: bool = False) -> bool:
    """
    Register .epi as an OS file type so double-clicking opens the viewer.

    Uses user-level settings only — no admin/root required.
    Idempotent: skips if already registered unless force=True.

    Args:
        silent: If True, never print or raise on failure.
        force: If True, re-register even if flag file exists.

    Returns:
        True if registration was performed, False if skipped or failed.
    """
    if not force and not _needs_registration():
        return False

    try:
        if sys.platform == "win32":
            register_windows()
        elif sys.platform == "darwin":
            register_macos()
        else:
            register_linux()

        _set_registration_state()

        if not silent:
            print("[OK] .epi file association registered successfully.")
            if sys.platform == "darwin":
                print("   If double-click doesn't work yet on macOS, log out and back in, ")
                print("   or run: killall Finder")
        return True

    except Exception as e:
        if not silent:
            print(f"[WARNING] Could not register file association: {e}")
            print("    Run: epi associate   to retry manually")
        return False


def unregister_file_association(silent: bool = False) -> bool:
    """
    Remove .epi file association from the OS.

    Args:
        silent: If True, never print or raise on failure.

    Returns:
        True if unregistration succeeded, False on failure.
    """
    try:
        if sys.platform == "win32":
            unregister_windows()
        elif sys.platform == "darwin":
            unregister_macos()
        else:
            unregister_linux()

        _clear_registered()

        if not silent:
            print("[OK] .epi file association removed.")
        return True

    except Exception as e:
        if not silent:
            print(f"[WARNING] Could not remove file association: {e}")
        return False

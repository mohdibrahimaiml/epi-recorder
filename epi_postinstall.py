"""
EPI Post-Installation Script
Automatically registers file associations after pip install.
"""
import sys
from pathlib import Path


def get_scripts_dir() -> Path | None:
    """Where pip puts console scripts for this interpreter.

    ``epi doctor`` uses this to repair a PATH that is missing the directory the
    ``epi`` command was actually installed into, instead of guessing.
    """
    import sysconfig

    try:
        scripts = sysconfig.get_path("scripts")
    except KeyError:
        return None
    return Path(scripts) if scripts else None


def add_to_user_path_windows(scripts_dir: Path) -> bool:
    """Append ``scripts_dir`` to the current user's PATH. True if it changed.

    User PATH, not machine PATH: no administrator rights, and the user can undo
    it. The registry is edited directly rather than with ``setx``, which
    silently truncates the value at 1024 characters - a real risk on machines
    with a long PATH.
    """
    if sys.platform != "win32":
        return False

    import winreg

    wanted = str(scripts_dir).rstrip("\\/")
    if not wanted:
        return False

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
    )
    try:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ
        if not isinstance(current, str):
            current = str(current or "")
        existing = [p.strip().rstrip("\\/") for p in current.split(";") if p.strip()]
        if any(p.lower() == wanted.lower() for p in existing):
            return False
        updated = current.rstrip(";") + (";" if current.strip() else "") + wanted
        if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            value_type = winreg.REG_EXPAND_SZ
        winreg.SetValueEx(key, "Path", 0, value_type, updated)
    finally:
        winreg.CloseKey(key)
    return True


def main():
    try:
        from epi_core.platform.associate import register_file_association
        # Silently register on install. 
        # This will now use the hardened path discovery I just implemented.
        register_file_association(silent=True)  # sets up Windows .epi double-click
        print("[OK] Registered .epi file association. Double-click .epi files to open them.")
    except Exception as e:
        print(f"[INFO] Could not register .epi association automatically. Run: epi associate ({e})")

if __name__ == "__main__":
    main()

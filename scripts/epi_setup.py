
import os
import sys
import site
import platform
import subprocess
from pathlib import Path

def setup_epi_path():
    print("EPI Recorder Setup - Windows Path Fixer")
    print("=" * 50)

    if platform.system() != "Windows":
        print("This script is designed for Windows only.")
        return

    # 1. Find where 'epi.exe' lives
    user_site = site.getusersitepackages()
    
    # Logic for Python 3.11+ Windows App Store installs:
    # site-packages: .../LocalCache/local-packages/Python311/site-packages
    # Scripts:       .../LocalCache/local-packages/Scripts
    
    site_packages = Path(user_site)
    # Go up 3 levels to find 'local-packages' root
    # from: .../local-packages/Python311/site-packages
    # to:   .../local-packages
    
    possible_roots = [
        site_packages.parent.parent.parent, # If in Python311/site-packages
        site_packages.parent,               # If in site-packages
        Path(site.getuserbase()),           # Standard API
        Path(sys.executable).parent         # Global
    ]
    
    epi_exe = None
    scripts_dir = None
    
    for root in possible_roots:
        check_scripts = root / "Scripts"
        check_exe = check_scripts / "epi.exe"
        if check_exe.exists():
            scripts_dir = check_scripts
            epi_exe = check_exe
            break

    if not epi_exe:
        # Fallback to hardcoded commonly known path if detection fails
        hardcoded_path = Path(r"C:\Users\dell\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\LocalCache\local-packages\Scripts")
        if (hardcoded_path / "epi.exe").exists():
            scripts_dir = hardcoded_path
            epi_exe = hardcoded_path / "epi.exe"

    if not epi_exe:
        print("[WARN] Could not automatically find 'epi.exe'.")
        print(f"Checked roots: {possible_roots}")
        print("Did you run 'pip install epi-recorder' yet?")
        return

    print(f"[OK] Found EPI at: {epi_exe}")
    
    # 2. Check if this path is in the User Environment PATH
    current_path = os.environ.get("PATH", "")
    
    if str(scripts_dir).lower() in current_path.lower():
        print("[OK] The path is already in your environment.")
        print("If 'epi' still doesn't work, try restarting your terminal.")
        return

    # 3. Add to User Path via Registry
    print("\n[INFO] Adding to System PATH...")
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            old_path_value, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            old_path_value = ""
            
        if str(scripts_dir).lower() not in old_path_value.lower():
            new_path_value = f"{old_path_value};{str(scripts_dir)}" if old_path_value else str(scripts_dir)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path_value)
            print("[OK] Successfully updated Registry PATH.")
            print("\n" + "=" * 50)
            print("[SUCCESS] Path fixed.")
            print("PLEASE CLOSE THIS TERMINAL AND OPEN A NEW ONE.")
            print("Type 'epi --version' to verify.")
            print("=" * 50)
        else:
             print("[OK] Path was already in Registry (pending restart).")
             
        winreg.CloseKey(key)
        
    except Exception as e:
        print(f"[FAIL] Failed to update registry: {e}")
        print("Try running this script as Administrator.")

if __name__ == "__main__":
    setup_epi_path()



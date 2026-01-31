"""
Post-installation script for EPI Recorder
Automatically fixes PATH issues on Windows for better UX
"""
import sys
import os
import platform
import subprocess
from pathlib import Path


def get_scripts_dir():
    """Get the Scripts directory where pip installs executables"""
    if platform.system() == "Windows":
        # Get the site-packages directory
        import site
        user_site = site.getusersitepackages()
        if user_site:
            # Scripts is typically ../Scripts relative to site-packages
            scripts_dir = Path(user_site).parent / "Scripts"
            if scripts_dir.exists():
                return scripts_dir
        
        # Fallback: try to find it from pip
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "epi-recorder"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Location:'):
                        location = line.split(':', 1)[1].strip()
                        scripts_dir = Path(location).parent / "Scripts"
                        if scripts_dir.exists():
                            return scripts_dir
        except Exception:
            pass
    
    return None


def is_in_path(directory):
    """Check if directory is in PATH"""
    path_env = os.environ.get('PATH', '')
    path_dirs = path_env.split(os.pathsep)
    dir_str = str(directory)
    return any(os.path.normcase(p) == os.path.normcase(dir_str) for p in path_dirs)


def add_to_user_path_windows(directory):
    """Add directory to user PATH on Windows"""
    try:
        import winreg
        
        # Open the user environment variables key
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            'Environment',
            0,
            winreg.KEY_READ | winreg.KEY_WRITE
        )
        
        try:
            # Get current PATH
            current_path, _ = winreg.QueryValueEx(key, 'Path')
        except WindowsError:
            current_path = ''
        
        # Add our directory if not already there
        path_parts = current_path.split(os.pathsep)
        dir_str = str(directory)
        
        if not any(os.path.normcase(p) == os.path.normcase(dir_str) for p in path_parts):
            new_path = current_path + os.pathsep + dir_str
            winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)
            
            # Broadcast WM_SETTINGCHANGE to notify the system
            try:
                import ctypes
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x1A
                ctypes.windll.user32.SendMessageW(
                    HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment'
                )
            except Exception:
                pass
            
            return True
        
        winreg.CloseKey(key)
        return False
        
    except Exception as e:
        print(f"Warning: Could not modify PATH: {e}")
        return False


def check_epi_command():
    """Check if 'epi' command is accessible"""
    try:
        result = subprocess.run(
            ['epi', '--version'],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def post_install():
    """Main post-install function"""
    print("\n" + "="*70)
    print("🎉 EPI Recorder Installation Complete!")
    print("="*70)
    
    # Check if epi command works
    if check_epi_command():
        print("\n✅ The 'epi' command is ready to use!")
        print("\nTry it now:")
        print("  epi --help")
        print("  epi init")
        return
    
    # If not, try to fix it (Windows only for now)
    if platform.system() == "Windows":
        print("\n⚠️  'epi' command not found in PATH")
        print("🔧 Attempting automatic fix...")
        
        scripts_dir = get_scripts_dir()
        
        if scripts_dir and scripts_dir.exists():
            print(f"📁 Found Scripts directory: {scripts_dir}")
            
            if not is_in_path(scripts_dir):
                print("➕ Adding to your user PATH...")
                
                try:
                    if add_to_user_path_windows(scripts_dir):
                        print("\n✅ SUCCESS! PATH updated.")
                        print("\n⚠️  IMPORTANT: You must restart your terminal for changes to take effect!")
                        print("\nAfter restarting your terminal, try:")
                        print("  epi --help")
                        print("  epi init")
                    else:
                        print("\n⚠️  Scripts directory already in PATH, but 'epi' not found.")
                        print("This might require a terminal restart.")
                        print("\nIf 'epi' still doesn't work after restarting, use:")
                        print(f"  python -m epi_cli")
                except Exception as e:
                    print(f"\n❌ Automatic fix failed: {e}")
                    show_manual_instructions(scripts_dir)
            else:
                print("✅ Scripts directory is in PATH")
                print("⚠️  You may need to restart your terminal for the command to work.")
        else:
            print("❌ Could not locate Scripts directory")
            show_fallback_instructions()
    else:
        # Linux/Mac
        print("\n⚠️  'epi' command not found in PATH")
        print("\nIf 'epi' doesn't work, use:")
        print("  python -m epi_cli")
        print("\nOr add pip's user base bin directory to PATH:")
        print("  export PATH=$PATH:$(python -m site --user-base)/bin")
    
    print("\n" + "="*70 + "\n")


def show_manual_instructions(scripts_dir):
    """Show manual PATH update instructions"""
    print("\n📖 MANUAL FIX REQUIRED:")
    print("\nOption 1: Update PATH (Permanent)")
    print("  1. Press Win + R, type: sysdm.cpl")
    print("  2. Advanced → Environment Variables")
    print("  3. Under 'User variables', select 'Path' → Edit")
    print("  4. Click 'New' and add:")
    print(f"     {scripts_dir}")
    print("  5. Click OK, restart your terminal")
    print("\nOption 2: Use python -m (Always works)")
    print("  python -m epi_cli run script.py")


def show_fallback_instructions():
    """Show fallback instructions if automatic fix fails"""
    print("\n📖 WORKAROUND:")
    print("\nUse 'python -m epi_cli' instead of 'epi':")
    print("  python -m epi_cli --help")
    print("  python -m epi_cli run script.py")
    print("  python -m epi_cli view recording.epi")


if __name__ == "__main__":
    post_install()



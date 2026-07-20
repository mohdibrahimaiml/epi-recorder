"""
EPI Post-Installation Script
Automatically registers file associations after pip install.
"""
import sys

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

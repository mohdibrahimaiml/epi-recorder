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
        register_file_association(silent=True)
        print("[OK] EPI post-install: File association registered.")
    except Exception as e:
        print(f"[INFO] EPI post-install: Association skipped ({e})")

if __name__ == "__main__":
    main()

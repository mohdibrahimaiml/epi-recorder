"""Check key status"""
from epi_cli.keys import KeyManager

km = KeyManager()
print(f"Keys directory: {km.keys_dir}")
print(f"Directory exists: {km.keys_dir.exists()}")
print(f"Has default key: {km.has_key('default')}")

if km.keys_dir.exists():
    print(f"Contents: {list(km.keys_dir.iterdir())}")



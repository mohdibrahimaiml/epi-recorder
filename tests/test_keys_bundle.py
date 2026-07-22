"""Trust bundle export/import for enterprise key distribution."""

from pathlib import Path

from epi_core.keys import KeyManager, export_trust_bundle, import_trust_bundle
from epi_core.trust import TrustRegistry


def test_export_import_trust_bundle(tmp_path: Path):
    keys_dir = tmp_path / "keys"
    trust_a = tmp_path / "trust_a"
    trust_b = tmp_path / "trust_b"
    km = KeyManager(keys_dir=keys_dir)
    km.generate_keypair("org-seal")

    bundle = export_trust_bundle(
        km,
        tmp_path / "bundle.zip",
        names=["org-seal"],
        trusted_keys_dir=trust_a,
    )
    assert bundle.exists()

    imported = import_trust_bundle(bundle, trusted_keys_dir=trust_b)
    assert len(imported) == 1
    assert imported[0].name == "org-seal.pub"
    hex_key = imported[0].read_text(encoding="utf-8").strip()
    assert len(bytes.fromhex(hex_key)) == 32

    # TrustRegistry sees the key
    reg = TrustRegistry(trusted_keys_dir=trust_b)
    ok, name, detail = reg.verify_key_trust(hex_key)
    assert ok is True
    assert name == "org-seal"

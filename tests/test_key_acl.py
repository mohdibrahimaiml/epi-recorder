"""Private keys must be owner-only on every platform.

On Unix that is ``chmod 0600``. On Windows the profile ACL is inherited and
can include unrelated SIDs, so ``epi keys generate`` applies an explicit
``icacls`` ACL (remove inheritance, grant only the current user).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from epi_core.keys import KeyManager, key_acl_advice


def test_generated_private_key_is_owner_only(tmp_path: Path) -> None:
    km = KeyManager(keys_dir=tmp_path / "keys")
    private_path, public_path = km.generate_keypair("default")

    assert private_path.exists()
    assert public_path.exists()
    assert key_acl_advice(km.keys_dir) is None

    if os.name != "nt":
        mode = private_path.stat().st_mode & 0o777
        assert mode == 0o600, oct(mode)


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL check")
def test_windows_private_key_acl_has_no_extra_principals(tmp_path: Path) -> None:
    from epi_core.keys import _icacls_extra_principals

    km = KeyManager(keys_dir=tmp_path / "keys")
    private_path, _ = km.generate_keypair("default")
    assert _icacls_extra_principals(private_path) == []

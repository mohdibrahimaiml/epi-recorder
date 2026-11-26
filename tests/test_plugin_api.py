"""E3: the versioned plugin interface must exist and resolve every name."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

import epi_recorder.plugin_api as plugin_api

PACKAGE = Path(plugin_api.__file__).parent
SUBMODULES = sorted(m.name for m in pkgutil.iter_modules(plugin_api.__path__))


def test_interface_version_is_declared() -> None:
    assert plugin_api.PLUGIN_API_VERSION == "1.0"


def test_every_submodule_declares_and_resolves_its_exports() -> None:
    assert SUBMODULES, "plugin_api has no submodules"
    for name in SUBMODULES:
        module = importlib.import_module(f"epi_recorder.plugin_api.{name}")
        exported = getattr(module, "__all__", None)
        assert exported, f"{name} has no __all__"
        missing = [symbol for symbol in exported if not hasattr(module, symbol)]
        assert not missing, f"{name} does not resolve {missing}"


@pytest.mark.parametrize(
    "module,public_name",
    [
        ("verification", "verify_step_chain"),
        ("timestamps", "tsa_url"),
        ("timestamps", "submit_rfc3161"),
        ("timestamps", "parse_tsr_gen_time"),
        ("delivery", "read_witness_outbox"),
        ("transparency", "local_service_public_key"),
        ("transparency", "register_local_statement"),
        ("signing", "verify_manifest_signature"),
        ("artifacts", "open_artifact"),
    ],
)
def test_private_helpers_have_a_public_name(module: str, public_name: str) -> None:
    mod = importlib.import_module(f"epi_recorder.plugin_api.{module}")
    assert callable(getattr(mod, public_name))


def test_plugin_api_never_imports_the_paid_package() -> None:
    import re

    pattern = re.compile(r"^\s*(?:from|import)\s+epi_enterprise\b", re.MULTILINE)
    offenders: list[str] = []
    for path in PACKAGE.glob("*.py"):
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert offenders == [], (
        "the public plugin interface must not depend on the paid package: "
        f"{offenders}"
    )

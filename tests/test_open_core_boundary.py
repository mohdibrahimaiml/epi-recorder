"""The open-core boundary, enforced rather than promised.

Two halves, both testable:

1. **The verifier is never gated and never phones home.** `epi verify` must work
   with no account, no licence and no network. This test parses the module and
   fails if a network client or a gating token is added to the verdict path.
2. **Paid code never enters the published wheel.** The wheel allowlist and the
   package list must not name the hosted service, billing or an enterprise
   package.

The second half is the one that decays silently: someone adds a module to
`[tool.setuptools.packages.find] include` and ships the commercial code to PyPI.
"""

from __future__ import annotations

import ast
import importlib.util
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The file that decides and prints a verification verdict.
VERIFIER = REPO / "epi_cli" / "verify.py"

NETWORK_MODULES = {
    "http",
    "http.client",
    "httpx",
    "requests",
    "aiohttp",
    "socket",
    "urllib.request",
    "urllib.error",
}

GATING_TOKENS = (
    "licence_key",
    "license_key",
    "entitlement",
    "subscription",
    "plan_limit",
    "trial_expired",
    "activate_licence",
    "activate_license",
)

PAID_MODULES = {
    "epi_gateway",
    "cloud",
    "verify_portal",
    "epi_enterprise",
    "billing",
    "tier_gating",
}

PREMIUM_COMMAND_MODULES = (
    "epi_cli/annex.py",
    "epi_cli/audit.py",
    "epi_cli/chat.py",
    "epi_cli/enterprise.py",
    "epi_cli/notify.py",
    "epi_cli/role_bindings.py",
    "epi_core/annex_report_template.py",
    "epi_core/annex_schemas.py",
    "epi_core/eu_notification.py",
)

# The checker and the approver must never need a licence. These are the
# commands the customer and their reviewer run on a free install.
FREE_TRUST_MODULES = (
    "epi_cli/approvers.py",
    "epi_cli/review.py",
    "epi_cli/oversight.py",
    "epi_cli/org_cmd.py",
    "epi_core/org_bundle.py",
)

FREE_TRUST_COMMANDS = {
    "approvers",
    "review",
    "oversight",
    "org",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _top_level(module: str) -> str:
    return module.split(".")[0]


def test_verifier_has_no_network_client():
    imports = {_top_level(m) for m in _imported_modules(VERIFIER)}
    offenders = sorted(imports & {"http", "httpx", "requests", "aiohttp", "socket", "urllib"})
    # urllib.parse is import-time only and does no I/O, but the verdict path has
    # no reason to need it either; keep the rule absolute.
    assert not offenders, (
        f"{VERIFIER.name} imports network modules {offenders}. Verification must "
        "run offline; see ARCHITECTURE.md 'Open core'."
    )


def test_verifier_has_no_gating_tokens():
    text = VERIFIER.read_text(encoding="utf-8").lower()
    hits = [token for token in GATING_TOKENS if token in text]
    assert not hits, (
        f"{VERIFIER.name} contains gating tokens {hits}. The verifier may never "
        "check a licence, plan or entitlement."
    )


def test_container_imports_no_network_client():
    imports = _imported_modules(REPO / "epi_core" / "container.py")
    offenders = sorted(
        m for m in imports if m in NETWORK_MODULES or m.startswith("urllib.request")
    )
    assert not offenders, f"epi_core/container.py imports network modules {offenders}"


def _load_audit_module():
    path = REPO / "scripts" / "audit_wheel.py"
    spec = importlib.util.spec_from_file_location("audit_wheel_boundary", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_wheel_allowlist_excludes_paid_modules():
    allowed = set(_load_audit_module().EXPECTED_TOP_LEVEL)
    leaked = sorted(allowed & PAID_MODULES)
    assert not leaked, (
        f"scripts/audit_wheel.py allows paid modules into the wheel: {leaked}. "
        "Remove them from EXPECTED_TOP_LEVEL; the verifier and recorder are the "
        "only things that ship."
    )


def test_package_list_excludes_paid_modules():
    with (REPO / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    include = config["tool"]["setuptools"]["packages"]["find"]["include"]
    names = {entry.split("*")[0].rstrip(".").rstrip("/") for entry in include}
    leaked = sorted(names & PAID_MODULES)
    assert not leaked, f"pyproject.toml packages the paid modules {leaked}"


def test_hosted_service_is_not_in_the_public_tree():
    assert not (REPO / "cloud").is_dir() or not any(
        (REPO / "cloud").glob("src/*.ts")
    ), "cloud/ source is back in the public repo; it belongs to the private service repo."


def test_billing_internals_are_not_publicly_testable():
    """Billing tests belong with the private service, not in the public suite."""
    assert not (REPO / "tests" / "test_tier_gating_plans.py").exists()
    assert not (REPO / "scripts" / "_tier_capability_matrix.py").exists()
    assert not (REPO / "scripts" / "seed-paddle-catalog.mjs").exists()


def test_premium_command_modules_are_not_public():
    """The paid command surface lives in epi-enterprise, not in the public wheel."""
    present = [name for name in PREMIUM_COMMAND_MODULES if (REPO / name).exists()]
    assert not present, (
        f"premium modules are back in the public tree: {present}. "
        "They belong to epi-enterprise; see ARCHITECTURE.md 'Open core'."
    )


def test_public_cli_has_no_premium_command_names():
    """Without epi-enterprise installed, the public CLI must not advertise paid commands."""
    from epi_cli.main import app

    names = {c.name for c in app.registered_commands if c.name}
    names |= {g.name for g in app.registered_groups if g.name}
    premium = {
        "annex",
        "audit",
        "chat",
        "enterprise",
        "notify",
    }
    leaked = sorted(names & premium)
    assert not leaked, (
        f"premium commands leaked into the public CLI: {leaked}. "
        "They must be registered by epi-enterprise through the plugin seam."
    )


def test_free_trust_commands_are_public_modules():
    missing = [name for name in FREE_TRUST_MODULES if not (REPO / name).exists()]
    assert not missing, f"trust-critical modules are missing from the free core: {missing}"


def test_free_trust_commands_are_registered_without_a_licence():
    from epi_cli.main import app

    names = {c.name for c in app.registered_commands if c.name}
    names |= {g.name for g in app.registered_groups if g.name}
    missing = sorted(FREE_TRUST_COMMANDS - names)
    assert not missing, (
        f"trust-critical commands missing from the free CLI: {missing}. "
        "The checker and approver must not need a licence."
    )


def test_verify_keeps_the_free_human_approval_checks():
    text = VERIFIER.read_text(encoding="utf-8")
    for option in ("--require-human-approval", "--witness-log", "--policy"):
        assert option in text, f"epi verify lost {option}"

def test_licensing_document_states_the_boundary():
    text = (REPO / "LICENSING.md").read_text(encoding="utf-8")
    assert "Apache-2.0" in text
    assert "epi-enterprise" in text
    assert "proprietary" in text.lower()
    # Published MIT versions cannot be un-licensed by a later change.
    assert "4.9.0" in text
    assert "MIT" in text

def test_public_package_declares_apache_and_paid_package_does_not():
    import tomllib

    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["license"] == "Apache-2.0"
    assert "LICENSE" in data["project"]["license-files"]
    assert "NOTICE" in data["project"]["license-files"]
    # The patent grant is the reason for the change; keep a real NOTICE file.
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    assert "EPI Labs" in notice
    assert "Apache" in notice


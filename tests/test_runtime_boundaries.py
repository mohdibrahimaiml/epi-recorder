import ast
from pathlib import Path

from epi_core.connectors import fetch_live_record as shared_fetch_live_record
from epi_core.keys import KeyManager as SharedKeyManager
from epi_cli.connect import fetch_live_record as cli_fetch_live_record
from epi_cli.keys import KeyManager as CliKeyManager


REPO_ROOT = Path(__file__).resolve().parents[1]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_cli_key_manager_reexports_shared_manager():
    assert CliKeyManager is SharedKeyManager


def test_cli_fetch_live_record_reexports_shared_function():
    assert cli_fetch_live_record is shared_fetch_live_record


def test_runtime_packages_do_not_import_cli_modules():
    runtime_files = [
        REPO_ROOT / "epi_gateway" / "main.py",
        REPO_ROOT / "epi_recorder" / "api.py",
    ]

    for path in runtime_files:
        modules = _imported_modules(path)
        assert "epi_cli" not in modules
        assert "epi_cli.keys" not in modules
        assert "epi_cli.connect" not in modules

from __future__ import annotations

from importlib import resources
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_text(package_dir: str, filename: str) -> str | None:
    try:
        return resources.files(package_dir).joinpath(filename).read_text(encoding="utf-8")
    except Exception:
        fallback = _repo_root() / package_dir / filename
        if fallback.exists():
            return fallback.read_text(encoding="utf-8")
        return None


def load_viewer_assets() -> dict[str, str | None]:
    return {
        "template_html": _read_text("web_viewer", "index.html"),
        "app_js": _read_text("web_viewer", "app.js"),
        "css_styles": _read_text("web_viewer", "styles.css"),
        "crypto_js": _read_text("epi_viewer_static", "crypto.js"),
    }

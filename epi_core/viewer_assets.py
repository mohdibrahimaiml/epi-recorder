from __future__ import annotations

from importlib import resources
from pathlib import Path

_VIEWER_STYLESHEET_TAG = '<link rel="stylesheet" href="styles.css">'
_VIEWER_JSZIP_TAG = '<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>'
_VIEWER_CRYPTO_TAG = '<script src="../epi_viewer_static/crypto.js"></script>'
_VIEWER_APP_TAG = '<script src="app.js"></script>'
_VIEWER_SCRIPT_BUNDLE = "\n".join((_VIEWER_JSZIP_TAG, _VIEWER_CRYPTO_TAG, _VIEWER_APP_TAG))


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
        "jszip_js": _read_text("web_viewer", "jszip.min.js"),
        "app_js": _read_text("web_viewer", "app.js"),
        "css_styles": _read_text("web_viewer", "styles.css"),
        "crypto_js": _read_text("epi_viewer_static", "crypto.js"),
    }


def inline_viewer_assets(
    template_html: str,
    *,
    css_styles: str | None,
    jszip_js: str | None,
    crypto_js: str | None,
    app_js: str | None,
    prepend_html: str = "",
) -> str:
    """
    Inline the browser viewer runtime into a single HTML document.

    This keeps extracted viewers and embedded viewers portable for offline and
    air-gapped review flows while still allowing a small preload payload to be
    injected ahead of the runtime scripts.
    """
    html = template_html

    style_block = f"<style>{css_styles}</style>" if css_styles else ""
    if _VIEWER_STYLESHEET_TAG in html:
        html = html.replace(_VIEWER_STYLESHEET_TAG, style_block)
    elif style_block and "</head>" in html:
        html = html.replace("</head>", f"{style_block}\n</head>", 1)

    script_parts: list[str] = []
    if prepend_html:
        script_parts.append(prepend_html)
    if jszip_js is not None:
        script_parts.append(f"<script>{jszip_js}</script>")
    if crypto_js is not None:
        script_parts.append(f"<script>{crypto_js}</script>")
    if app_js is not None:
        script_parts.append(f"<script>{app_js}</script>")
    script_block = "\n".join(part for part in script_parts if part)

    if _VIEWER_SCRIPT_BUNDLE in html:
        html = html.replace(_VIEWER_SCRIPT_BUNDLE, script_block)
        return html

    if prepend_html and prepend_html not in html:
        if "</head>" in html:
            html = html.replace("</head>", f"{prepend_html}\n</head>", 1)
        else:
            html = f"{prepend_html}\n{html}"

    replacements = (
        (_VIEWER_JSZIP_TAG, f"<script>{jszip_js}</script>" if jszip_js is not None else ""),
        (_VIEWER_CRYPTO_TAG, f"<script>{crypto_js}</script>" if crypto_js is not None else ""),
        (_VIEWER_APP_TAG, f"<script>{app_js}</script>" if app_js is not None else ""),
    )
    for needle, replacement in replacements:
        html = html.replace(needle, replacement)
    return html

from __future__ import annotations

from importlib import resources
from pathlib import Path
import re

_VIEWER_STYLESHEET_TAG = '<link rel="stylesheet" href="styles.css">'
_VIEWER_JSZIP_TAG = '<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>'
_VIEWER_CRYPTO_TAG = '<script src="../epi_viewer_static/crypto.js"></script>'
_VIEWER_APP_TAG = '<script src="app.js"></script>'
_VIEWER_SCRIPT_BUNDLE = "\n".join((_VIEWER_JSZIP_TAG, _VIEWER_CRYPTO_TAG, _VIEWER_APP_TAG))


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_text(package_dir: str, filename: str) -> str | None:
    fallback = _repo_root() / package_dir / filename
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    try:
        return resources.files(package_dir).joinpath(filename).read_text(encoding="utf-8")
    except Exception:
        return None


def load_viewer_assets(version: str = "1.0") -> dict[str, str | None]:
    assets = {
        "template_html": _read_text("web_viewer", "index.html"),
        "jszip_js": _read_text("web_viewer", "jszip.min.js"),
        "app_js": _read_text("web_viewer", "app.js"),
        "css_styles": _read_text("web_viewer", "styles.css"),
        "crypto_js": _read_text("epi_viewer_static", "crypto.js"),
    }
    _validate_app_js(assets["app_js"])
    return assets


def _validate_app_js(app_js: str | None) -> None:
    """Validate app.js before it gets inlined into any viewer.

    Single shared implementation (also used by tests/test_viewer_js_validation.py
    — one implementation, no duplicated slicing logic that can drift):
      1. Structural checks that are pure string matching (safe by construction:
         forbidden patterns, required symbols).
      2. Brace balance via a source-aware scan (comments, strings, and template
         literals with ${} are skipped — never naive .count() on raw text).
      3. Real grammar check via `node --check` when node is available
         (Node is a CI dependency; locally the structural checks still run and
         a missing node only downgrades to a warning, never a silent pass).
    """
    if not app_js:
        return

    import sys

    errors = validate_app_js_source(app_js)
    node_errors = node_check_js(app_js)
    if node_errors is None:
        print(
            "[EPI] node not found — pack-time JS syntax check skipped "
            "(structural check still ran)",
            file=sys.stderr,
        )
    else:
        errors.extend(node_errors)

    if errors:
        msg = "app.js validation failed:\n  " + "\n  ".join(errors)
        print(f"[EPI] {msg}", file=sys.stderr)
        raise RuntimeError(msg)


def validate_app_js_source(app_js: str) -> list[str]:
    """Shared structural validation: forbidden patterns, required symbols,
    source-aware brace balance. Pure Python, no subprocess. Returns errors."""
    errors: list[str] = []

    # Critical: old bug pattern must not return
    if "delete manifest.signature" in app_js:
        errors.append(
            "FATAL: 'delete manifest.signature' found in app.js — "
            "this destroys cryptographic integrity during Sign & Seal"
        )

    # Exact punt UI string (not comments that merely mention the bug by name)
    if "sigEl.textContent = 'OPEN VIA EPI VIEW TO VERIFY'" in app_js or (
        'sigEl.textContent = "OPEN VIA EPI VIEW TO VERIFY"' in app_js
    ):
        errors.append(
            "FATAL: signature UI still assigns OPEN VIA EPI VIEW TO VERIFY — "
            "standalone export-html must run real client-side signature verification"
        )

    if "function verifyCaseInBrowser" not in app_js and "async function verifyCaseInBrowser" not in app_js:
        errors.append(
            "FATAL: 'verifyCaseInBrowser' missing from app.js — "
            "export-html / embedded viewers cannot prove signatures offline"
        )

    # Critical: new function must exist
    if "buildReviewedFromOriginal" not in app_js:
        errors.append(
            "FATAL: 'buildReviewedFromOriginal' missing from app.js — "
            "Sign & Seal will produce corrupted artifacts"
        )

    if "buildReviewedArtifactBytes" not in app_js:
        errors.append(
            "FATAL: 'buildReviewedArtifactBytes' missing from app.js"
        )

    errors.extend(js_brace_errors(app_js))
    return errors


def js_brace_errors(source: str) -> list[str]:
    """Whole-file brace balance with string/comment/template awareness.

    No function slicing (slicing on the literal "function " is what broke
    when anonymous callbacks appeared — the slice boundary is a guess, the
    count after it fiction). Returns [] when balanced.
    """
    depth = 0
    # Template-literal stack: None = raw template text, int = brace depth
    # recorded at the matching ${ (a } returning to that depth resumes text).
    tmpl: list[int | None] = [None]  # base level behaves as CODE, not text
    mode = "code"
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if mode == "code":
            if ch == "/" and nxt == "/":
                mode = "line"
                i += 2
                continue
            if ch == "/" and nxt == "*":
                mode = "block"
                i += 2
                continue
            if ch == "'":
                mode = "sq"
            elif ch == '"':
                mode = "dq"
            elif ch == "`":
                tmpl.append(None)
                mode = "tpl"
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    return ["brace mismatch: closing } with nothing open"]
                if tmpl and tmpl[-1] is not None and depth == tmpl[-1]:
                    tmpl.pop()
                    mode = "tpl"
        elif mode == "line":
            if ch == "\n":
                mode = "code"
        elif mode == "block":
            if ch == "*" and nxt == "/":
                mode = "code"
                i += 2
                continue
        elif mode in ("sq", "dq"):
            quote = "'" if mode == "sq" else '"'
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                mode = "code"
            elif ch == "\n" and mode == "sq":
                # Unterminated single-quoted string continues in sloppy
                # parsing; do not let it swallow the rest of the file —
                # node --check owns true syntax, this scan only balances.
                mode = "code"
        elif mode == "tpl":
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                tmpl.pop()
                mode = "code"
            elif ch == "$" and nxt == "{":
                tmpl.append(depth)
                depth += 1
                mode = "code"
                i += 2
                continue
        i += 1
    if mode == "block":
        return ["brace scan: unterminated block comment"]
    if len(tmpl) > 1:
        return ["brace scan: unterminated template literal"]
    if mode in ("sq", "dq"):
        return ["brace scan: unterminated string literal"]
    if depth != 0:
        return [f"brace mismatch: {depth} unclosed {{ remaining"]
    return []


def node_check_js(app_js: str) -> list[str] | None:
    """Real-grammar syntax check via `node --check`. Returns None when node
    is unavailable (caller downgrades to a warning, never a silent pass)."""
    import shutil
    import subprocess
    import tempfile

    if shutil.which("node") is None:
        return None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(app_js)
            tmp = fh.name
        try:
            proc = subprocess.run(
                ["node", "--check", tmp],
                capture_output=True,
                text=True,
                timeout=60,
            )
        finally:
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass
        if proc.returncode == 0:
            return []
        detail = (proc.stderr or proc.stdout or "unknown syntax error").strip().splitlines()
        return [f"node --check failed: {detail[0][:200]}" if detail else "node --check failed"]
    except Exception as exc:
        return [f"node --check could not run: {exc}"]


def _escape_inline_script_source(script_source: str | None) -> str | None:
    if script_source is None:
        return None
    BS = chr(92)  # backslash character \
    # Escape "</script>" -> "</" + BS + "x2fscript>"
    script_source = re.sub(
        r"</(script>)",
        lambda m: "</" + BS + "x2f" + m.group(1),
        script_source,
        flags=re.IGNORECASE,
    )
    # Escape "<script" (followed by space, >, or word boundary) 
    # -> BS + "x3c" + "script" + rest
    script_source = re.sub(
        r"<(script[\b\s>])",
        lambda m: BS + "x3c" + m.group(1),
        script_source,
        flags=re.IGNORECASE,
    )
    return script_source


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
    html = template_html.replace("\r\n", "\n")
    jszip_js = _escape_inline_script_source(jszip_js)
    crypto_js = _escape_inline_script_source(crypto_js)
    app_js = _escape_inline_script_source(app_js)

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

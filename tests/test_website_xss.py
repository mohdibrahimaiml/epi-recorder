"""WP-SEC-1: no file-derived text may reach innerHTML unescaped (XSS).

Scans the verifier-surface files named in the plan and requires that every
``innerHTML`` sink either:
  * passes its dynamic parts through ``esc(`` / ``escapeHtml(``, or
  * carries ``// static-html`` (static literal, no attacker data), or
  * carries ``// esc-built-html`` (assigned var audited: built only from
    esc() output and static literals — see the comment at each use).

Rationale: the home-page and /verify/ verifiers parse attacker-controlled
``.epi`` files (file names, mimetype entry, manifest strings, exception
messages) on the same origin as the login token in localStorage. Any of
those reaching ``innerHTML`` unescaped executes script as epilabs.org.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]

# Exact scope from the plan (WP-SEC-1 "Do" step 2).
SCOPE = [
    REPO / "website" / "js" / "home-verify.js",
    REPO / "website" / "js" / "epi-verify-core.js",
    REPO / "website" / "cases" / "index.html",
    REPO / "website" / "verify" / "index.html",
    REPO / "website" / "assets" / "viewer.html",
]

SINK_RE = re.compile(r"\.innerHTML\s*=\s*(?P<rhs>.*)$")
BUILT_MARKER = "esc-built-html"
STATIC_MARKER = "static-html"

# Identifiers known to carry file-derived or error-derived text in
# website/js/home-verify.js. Every occurrence must sit inside esc(...).
# (mtNorm = zip mimetype entry, f.name = dropped file name,
#  e/ex.message = exception text that can quote file bytes.)
HOME_VERIFY_DANGEROUS = ("mtNorm", "f.name", "e.message", "ex.message")


def _joined_expression(lines, start):
    """Return the sink line, plus following lines if the RHS is multi-line."""
    first = lines[start]
    rhs_after = SINK_RE.search(first).group("rhs")
    single_line_complete = (
        rhs_after.count("`") % 2 == 0
        and not rhs_after.rstrip().endswith(("+", "=", "(", ",", "{", "=>"))
        and rhs_after.strip() != ""
    )
    if single_line_complete:
        return first
    # Multi-line RHS (template literal or chained call): audit the window.
    return "\n".join(lines[start : start + 16])


def _expression_is_safe(expr: str) -> bool:
    if BUILT_MARKER in expr or STATIC_MARKER in expr:
        return True
    if "esc(" in expr or "escapeHtml(" in expr:
        return True
    # Static literal: quoted/backtick string with no concatenation,
    # no interpolation, no identifiers.
    rhs = expr.split("=", 1)[-1].strip().rstrip(";")
    if re.fullmatch(r"(''|\".*?\"|'.*?'|`[^`$]*?`)", rhs, re.DOTALL):
        return True
    return False


def test_scope_files_exist():
    for path in SCOPE:
        assert path.is_file(), f"scope file missing: {path}"


def test_innerhtml_sinks_are_escaped_or_marked():
    violations = []
    for path in SCOPE:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for lineno, raw in enumerate(lines, 1):
            m = SINK_RE.search(raw)
            if not m:
                continue
            # `return div.innerHTML;` — the escape helper itself, not a sink.
            if re.search(r"\breturn\b.*\.innerHTML\s*;?\s*$", raw.strip()):
                continue
            expr = _joined_expression(lines, lineno - 1)
            if not _expression_is_safe(expr):
                first = raw.strip()
                violations.append(f"{path.name}:{lineno}: {first[:140]}")
    assert not violations, (
        "unescaped innerHTML sinks (wrap dynamic parts with esc()/escapeHtml() "
        f"or mark audited lines // {STATIC_MARKER} / // {BUILT_MARKER}):\n"
        + "\n".join(violations)
    )


def _sink_windows(lines):
    """Yield (lineno, line) for lines that can flow into an innerHTML sink.

    A sink renders either its own (possibly multi-line) expression or a
    variable accumulated over the preceding lines (``html += ...``), so the
    audit window covers 60 lines above through 16 below each sink.
    """
    sink_at = [
        i for i, raw in enumerate(lines) if SINK_RE.search(raw)
    ]
    in_window = set()
    for s in sink_at:
        for i in range(max(0, s - 60), min(len(lines), s + 17)):
            in_window.add(i)
    for i in sorted(in_window):
        yield i + 1, lines[i]


def test_template_interpolations_are_escaped():
    """Any ${...} that can reach innerHTML must go through esc()."""
    # Variables audited to hold only esc() output + static literals.
    ESC_BUILT_VARS = ("detailHtml",)
    violations = []
    for path in SCOPE:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        windows = list(_sink_windows(lines))
        for idx, (lineno, raw) in enumerate(windows):
            line = raw.strip()
            if "${" not in line:
                continue
            # Property assignments (textContent/title/style) never parse HTML.
            # (Continuations: the statement may start on the previous line.)
            prev = windows[idx - 1][1] if idx > 0 else ""
            if (
                "textContent" in line
                or ".title" in line
                or ".style." in line
                or "textContent" in prev
            ):
                continue
            # `parts` flows only to noteEl.textContent (audited); never innerHTML.
            if line.startswith("parts.push("):
                continue
            for interp in re.findall(r"\$\{([^}]*)\}", line):
                if "esc(" in interp or "escapeHtml(" in interp:
                    continue
                if interp.strip() in ESC_BUILT_VARS:
                    continue
                # Static ternary of string literals: no attacker data.
                if re.fullmatch(
                    r"""\s*[A-Za-z0-9_.]+\s*\?\s*('[^']*'|"[^"]*")\s*:\s*('[^']*'|"[^"]*")\s*""",
                    interp,
                ):
                    continue
                if STATIC_MARKER in line or BUILT_MARKER in line:
                    continue
                violations.append(f"{path.name}:{lineno}: ${{{interp}}}")
    assert not violations, (
        "unescaped template interpolations reaching innerHTML:\n"
        + "\n".join(violations)
    )


def test_home_verify_dangerous_sources_escaped():
    path = REPO / "website" / "js" / "home-verify.js"
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    violations = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        for ident in HOME_VERIFY_DANGEROUS:
            if ident not in line:
                continue
            if "esc(" in line:
                continue
            # Reading the source value is fine; the sink use must escape.
            if re.search(r"\bvar\s+mt\b|\bmtNorm\s*=", line):
                continue
            # report.identity.detail is escaped once at render by reportDOM's
            # esc(i.detail) (pinned by test_shared_case_honesty); storing it
            # raw avoids double-escaping.
            if re.search(r"identity\.detail\s*=", line):
                continue
            # Comparisons and non-HTML uses (extension checks, enum tests)
            # cannot execute script; only string building toward HTML matters.
            # (Strip string literals first: 'epi+zip' contains a harmless +.)
            no_strings = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", "", line)
            if not re.search(r"\+|\$\{|innerHTML|showResult|showReport|detail", no_strings):
                continue
            violations.append(f"home-verify.js:{lineno}: {line[:140]}")
    assert not violations, (
        "file-derived values reaching HTML without esc():\n" + "\n".join(violations)
    )


def test_home_verify_has_esc_helper():
    src = (REPO / "website" / "js" / "home-verify.js").read_text(
        encoding="utf-8", errors="ignore"
    )
    assert re.search(
        r"function esc\(s\)\{return String\(s\)\.replace", src
    ), "home-verify.js must define the esc() helper from the plan"

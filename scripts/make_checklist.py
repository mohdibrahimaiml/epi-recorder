#!/usr/bin/env python3
"""Build the one checklist: ten general questions, then four for insurance.

One source, one page, one PDF. The legacy plain-text path is written from the
same content so old links keep working and cannot drift.

    python scripts/make_checklist.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "website" / "assets"

OUT_PDF = ASSETS / "checklist.pdf"
OUT_TXT = ASSETS / "checklist.txt"
LEGACY_TXT = ASSETS / "decision-record-checklist.txt"

TITLE = "The AI decision record checklist"
SUBTITLE = "Ten questions for any AI decision, then four more for insurance"
LEDE = (
    "Pick one real decision the AI touched. Answer from the record itself, not "
    "from what the vendor could assemble for an exam. Every no is a gap."
)

GENERAL = [
    ("The decision", "What was decided, in plain language?"),
    ("Timing", "What outcome was recorded, and when?"),
    ("Inputs", "What inputs and data did the model rely on?"),
    ("Model", "Which model and version answered?"),
    ("Rules", "What rules, policy or limit applied?"),
    ("Reasons", "What reasons were recorded for the decision?"),
    ("Approval", "Who or what approved it, and when?"),
    ("Sign-off", "If a human approval was required, is it attached to this record?"),
    ("Outcome", "What happened next — the action taken or the customer outcome?"),
    ("Portability", "Can the reviewer read this without the vendor's system?"),
]

INSURANCE = [
    (
        "Human review",
        "Did the reviewer agree with the AI, change it, or override it?",
    ),
    (
        "Version in force",
        "Which version of the policy or rule was in force on the day of the decision?",
    ),
    (
        "Contemporaneous",
        "Was the record made at the time of the decision, not assembled later for an exam?",
    ),
    (
        "Tamper-evident",
        "Would the carrier notice if the record were changed after it was handed over?",
    ),
]

CLOSING = (
    "Start with the decisions that should have a record and do not. That list is "
    "usually the gap an examiner finds first, and the one a carrier cannot answer "
    "from the vendor's dashboard."
)

FOOTER = (
    "epilabs.org/checklist  |  "
    "Not legal advice. Check with your carrier and counsel."
)


def _numbered(items: list[tuple[str, str]], start: int) -> list[tuple[int, str, str]]:
    return [(i, label, q) for i, (label, q) in enumerate(items, start=start)]


def build_txt() -> str:
    lines = [f"# {TITLE}", "", SUBTITLE, "", LEDE, ""]
    lines += ["## The ten questions", ""]
    for i, label, q in _numbered(GENERAL, 1):
        lines += [f"{i}. {q}", f"   Field: {label}", ""]
    lines += ["## For insurance: four more questions", ""]
    for i, label, q in _numbered(INSURANCE, 11):
        lines += [f"{i}. {q}", f"   Field: {label}", ""]
    lines += [
        "## How to score",
        "",
        "One point per question you can answer from the record itself.",
        "",
        "| Score | What it means |",
        "|---|---|",
        "| 12-14 | A decision record a carrier can rely on. |",
        "| 8-11  | Close. Reasons, review or timing are incomplete. |",
        "| 4-7   | Observability data. You can debug it; a carrier cannot read it. |",
        "| 0-3   | Logs. The decision has to be reconstructed after the fact. |",
        "",
        CLOSING,
        "",
        FOOTER,
        "",
    ]
    return "\n".join(lines)


def _rows(items: list[tuple[int, str, str]]) -> str:
    return "\n".join(
        f"""
      <tr>
        <td class="num">{i}</td>
        <td>
          <div class="q">{q}</div>
          <div class="field">{label}</div>
        </td>
      </tr>"""
        for i, label, q in items
    )


def build_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{TITLE}</title>
<style>
  @page {{ size: A4; margin: 14mm 16mm 12mm 16mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color: #11161d; margin: 0; font-size: 10pt; line-height: 1.4; }}
  .eyebrow {{ font-size: 8pt; letter-spacing: .12em; text-transform: uppercase;
              color: #5b6673; font-weight: 600; }}
  h1 {{ font-size: 19pt; line-height: 1.15; margin: 5pt 0 2pt; letter-spacing: -.01em; }}
  .sub {{ font-size: 10.5pt; color: #33404f; margin: 0 0 7pt; }}
  .lede {{ font-size: 9pt; color: #4a5666; margin: 0 0 8pt; max-width: 160mm; }}
  h2 {{ font-size: 10.5pt; margin: 9pt 0 2pt; color: #0b6b4f; }}
  table {{ width: 100%; border-collapse: collapse; }}
  tr {{ border-top: 0.6pt solid #d7dde4; }}
  tr:last-child {{ border-bottom: 0.6pt solid #d7dde4; }}
  td {{ padding: 3.6pt 0; vertical-align: top; }}
  td.num {{ width: 10mm; font-weight: 700; color: #0b6b4f; font-size: 10.5pt; }}
  .q {{ font-size: 10pt; color: #11161d; }}
  .field {{ font-size: 7.6pt; color: #6b7684; margin-top: 0.5pt; }}
  .score {{ margin-top: 8pt; font-size: 8.4pt; color: #4a5666; }}
  .score strong {{ color: #11161d; }}
  .closing {{ margin-top: 5pt; font-size: 8.4pt; color: #4a5666; }}
  .foot {{ position: fixed; bottom: 0; left: 0; right: 0; font-size: 7.2pt;
           color: #7b8593; border-top: 0.6pt solid #e3e8ee; padding-top: 3pt; }}
</style>
</head>
<body>
  <div class="eyebrow">One record per decision</div>
  <h1>{TITLE}</h1>
  <p class="sub">{SUBTITLE}</p>
  <p class="lede">{LEDE}</p>

  <h2>The ten questions</h2>
  <table>
{_rows(_numbered(GENERAL, 1))}
  </table>

  <h2>For insurance: four more questions</h2>
  <table>
{_rows(_numbered(INSURANCE, 11))}
  </table>

  <p class="score"><strong>How to score:</strong> one point per question you can answer from the record itself.
    12–14 a decision record a carrier can rely on · 8–11 close, but reasons, review or timing are incomplete ·
    4–7 observability data · 0–3 logs. <strong>Every no is a gap.</strong></p>
  <p class="closing">{CLOSING}</p>
  <div class="foot">{FOOTER}</div>
</body>
</html>
"""


def main() -> int:
    text = build_txt()
    OUT_TXT.write_text(text, encoding="utf-8")
    LEGACY_TXT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT_TXT.relative_to(ROOT)}")
    print(f"wrote {LEGACY_TXT.relative_to(ROOT)}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(build_html(), wait_until="load")
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
    print(f"wrote {OUT_PDF.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

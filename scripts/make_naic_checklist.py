#!/usr/bin/env python3
"""Build the NAIC vendor checklist: one plain-text file and one PDF.

The questions live here once so the web page, the downloadable text file and the
PDF cannot drift apart.

    python scripts/make_naic_checklist.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_TXT = ROOT / "website" / "assets" / "naic-ai-decision-record-checklist.txt"
OUT_PDF = ROOT / "website" / "assets" / "naic-ai-decision-record-checklist.pdf"

TITLE = "The minimum AI decision record"
SUBTITLE = "Ten questions for an insurance AI vendor, per decision"
LEDE = (
    "Pick one real decision the AI touched. Answer from the record itself, not "
    "from what the vendor could assemble for an exam. Every no is a gap."
)

QUESTIONS = [
    ("Inputs", "For one specific decision, can you show what data the AI saw?"),
    ("Decision and reasons", "Can you show what it recommended or decided, and why?"),
    (
        "Policy and version",
        "Which policy provisions or rules did it rely on, and which version was in force that day?",
    ),
    (
        "Model and version",
        "Which model and version answered, and would the record show if it changed later?",
    ),
    (
        "Human review",
        "Who reviewed it, and did they agree, change or override the AI?",
    ),
    ("Time", "When did each step happen?"),
    (
        "Contemporaneous",
        "Was the record made at the time of the decision, not assembled later for an exam?",
    ),
    (
        "Portable",
        "Can the carrier open it without logging into the vendor's system?",
    ),
    (
        "Tamper-evident",
        "Would the carrier notice if the record were changed after it was handed over?",
    ),
    (
        "Coverage",
        "Can you list decisions that should have a record but don't?",
    ),
]

FOOTER = (
    "epilabs.org/insurance/ai-vendor-decision-record  |  "
    "Not legal advice. Check with your carrier and counsel.  |  "
    "Not affiliated with the NAIC."
)


def build_txt() -> str:
    lines = [f"# {TITLE}", "", SUBTITLE, "", LEDE, ""]
    for i, (label, question) in enumerate(QUESTIONS, start=1):
        lines.append(f"{i}. {question}")
        lines.append(f"   Field: {label}")
        lines.append("")
    lines += [
        "## How to score",
        "",
        "One point per question you can answer from the record itself.",
        "",
        "| Score | What it means |",
        "|---|---|",
        "| 9-10 | A decision record a carrier can rely on. |",
        "| 6-8  | Close. Reasons, review or timing are incomplete. |",
        "| 3-5  | Observability data. You can debug it; a carrier cannot read it. |",
        "| 0-2  | Logs. The decision has to be reconstructed after the fact. |",
        "",
        "Every no is a gap. The readiness assessment closes them.",
        "",
        FOOTER,
        "",
    ]
    return "\n".join(lines)


def build_html() -> str:
    rows = "\n".join(
        f"""
      <tr>
        <td class="num">{i}</td>
        <td>
          <div class="q">{question}</div>
          <div class="field">{label}</div>
        </td>
      </tr>"""
        for i, (label, question) in enumerate(QUESTIONS, start=1)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{TITLE} — {SUBTITLE}</title>
<style>
  @page {{ size: A4; margin: 16mm 16mm 14mm 16mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color: #11161d; margin: 0; font-size: 10.5pt; line-height: 1.45; }}
  .eyebrow {{ font-size: 8pt; letter-spacing: .12em; text-transform: uppercase;
              color: #5b6673; font-weight: 600; }}
  h1 {{ font-size: 21pt; line-height: 1.15; margin: 6pt 0 2pt; letter-spacing: -.01em; }}
  .sub {{ font-size: 11pt; color: #33404f; margin: 0 0 10pt; }}
  .lede {{ font-size: 9.5pt; color: #4a5666; margin: 0 0 14pt; max-width: 150mm; }}
  table {{ width: 100%; border-collapse: collapse; }}
  tr {{ border-top: 0.6pt solid #d7dde4; }}
  tr:last-child {{ border-bottom: 0.6pt solid #d7dde4; }}
  td {{ padding: 5.2pt 0; vertical-align: top; }}
  td.num {{ width: 12mm; font-weight: 700; color: #0b6b4f; font-size: 11pt; }}
  .q {{ font-size: 10.5pt; color: #11161d; }}
  .field {{ font-size: 8pt; color: #6b7684; margin-top: 1pt; }}
  .score {{ margin-top: 12pt; font-size: 8.8pt; color: #4a5666; }}
  .score strong {{ color: #11161d; }}
  .notes {{ margin-top: 10pt; font-size: 8.8pt; color: #4a5666; }}
  .notes p {{ margin: 0 0 5pt; max-width: 165mm; }}
  .notes strong {{ color: #11161d; }}
  .foot {{ position: fixed; bottom: 0; left: 0; right: 0; font-size: 7.4pt;
           color: #7b8593; border-top: 0.6pt solid #e3e8ee; padding-top: 4pt; }}
</style>
</head>
<body>
  <div class="eyebrow">For carriers and the AI vendors who serve them</div>
  <h1>{TITLE}</h1>
  <p class="sub">{SUBTITLE}</p>
  <p class="lede">{LEDE}</p>
  <table>
{rows}
  </table>
  <p class="score"><strong>How to score:</strong> one point per question you can answer from the record itself.
    9–10 a decision record a carrier can rely on · 6–8 close, but reasons, review or timing are incomplete ·
    3–5 observability data · 0–2 logs. <strong>Every no is a gap.</strong></p>
  <div class="notes">
    <p><strong>What it does not ask for.</strong> None of these ten questions needs the vendor's source code,
       training data or model weights. They ask what happened in one decision and whether a person can read it.</p>
    <p><strong>How to use it.</strong> Take one real decision the AI touched. If you cannot answer a question
       from the record, that is the gap to close before an examiner asks. A worked example, with invented
       claim data and a real override, is at epilabs.org/insurance/ai-vendor-decision-record.</p>
  </div>
  <div class="foot">{FOOTER}</div>
</body>
</html>
"""


def main() -> int:
    OUT_TXT.write_text(build_txt(), encoding="utf-8")
    print(f"wrote {OUT_TXT.relative_to(ROOT)}")

    from playwright.sync_api import sync_playwright

    html = build_html()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
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

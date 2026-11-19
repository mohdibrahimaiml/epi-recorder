from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]  # website/
html_files = list(root.glob("*.html"))
if (root / "verify").is_dir():
    html_files += list((root / "verify").glob("*.html"))

skip_names = {"_nav.html", "nav-partial.html", "viewer.html"}


def upgrade(text: str, path: Path) -> str:
    text = re.sub(r'href="(/?css/epi\.css)\?v=\d+"', r'href="\1?v=29"', text)
    text = re.sub(r'href="(/?css/epi-v2\.css)\?v=\d+"', r'href="\1?v=9"', text)
    text = re.sub(r'href="(/?css/polish\.css)\?v=\d+"', r'href="\1?v=3"', text)
    text = re.sub(r'href="(/?css/wow\.css)\?v=\d+"', r'href="\1?v=2"', text)

    if "css/wow.css" not in text and "css/epi-v2.css" in text:
        m = re.search(r'(<link rel="stylesheet" href="(/?css/epi-v2\.css)\?v=\d+"\s*/?>)', text)
        if m:
            prefix = "/" if m.group(2).startswith("/") else ""
            inject = (
                f'{m.group(1)}\n'
                f'<link rel="stylesheet" href="{prefix}css/polish.css?v=3">\n'
                f'<link rel="stylesheet" href="{prefix}css/wow.css?v=2">'
            )
            text = text.replace(m.group(1), inject, 1)

    if "wow.js" not in text and "epi-instrument" in text:
        if "</body>" in text:
            uses_abs = 'href="/css/' in text or 'src="/js/' in text
            src = "/js/wow.js?v=2" if uses_abs or "verify" in path.as_posix() else "js/wow.js?v=2"
            text = text.replace("</body>", f'<script src="{src}"></script>\n</body>', 1)

    text = re.sub(r'src="(/?js/wow\.js)\?v=\d+"', r'src="\1?v=2"', text)
    return text


changed = []
for p in sorted(html_files):
    if p.name in skip_names:
        continue
    t = p.read_text(encoding="utf-8")
    nt = upgrade(t, p)
    if nt != t:
        p.write_text(nt, encoding="utf-8")
        changed.append(p.relative_to(root).as_posix())

print("Updated", len(changed), "files:")
for c in changed:
    print(" ", c)

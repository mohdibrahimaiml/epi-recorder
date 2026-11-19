from pathlib import Path
p = Path(__file__).resolve().parents[2] / "js" / "home-verify.js"
js = p.read_text(encoding="utf-8")
if not js.strip().startswith("(function"):
    p.write_text('(function(){\n"use strict";\n' + js + "\n})();\n", encoding="utf-8")
    print("wrapped")
else:
    print("already wrapped")
print("len", p.stat().st_size)

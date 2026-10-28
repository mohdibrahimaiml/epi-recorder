"""Build sentence-level WebVTT captions for the launch film from the VO script.

Each VO segment's text is split into sentences and its measured duration is
distributed by character share. Timings are approximate but stable: they are
derived from the same vo.json and VO_AT constants the score uses, so captions
never drift away from the mix.

Output: assets/audio/epi-launch.vtt
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "assets" / "audio"

VO_AT = {"vo1": 0.8, "vo2": 12.4, "vo3": 24.4, "vo4": 37.1, "vo5": 50.5}
GAP = 0.10  # breath between cues


def ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def sentences(text: str) -> list[str]:
    out: list[str] = []
    cur = ""
    for ch in text:
        cur += ch
        if ch in ".!?" and len(cur.strip()) > 2:
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        out.append(cur.strip())
    return out


def main() -> None:
    meta = json.loads((AUDIO / "vo.json").read_text(encoding="utf-8"))
    lines = ["WEBVTT", ""]
    for seg in meta:
        start = VO_AT[seg["id"]]
        dur = float(seg["duration"])
        parts = sentences(seg["text"])
        total = sum(len(p) for p in parts) or 1
        t = start
        for part in parts:
            share = dur * len(part) / total
            end = min(start + dur, t + max(0.9, share))
            lines += [f"{ts(t)} --> {ts(end)}", part, ""]
            t = end + GAP

    out = AUDIO / "epi-launch.vtt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}  ({len(meta)} segments, {sum(len(sentences(m['text'])) for m in meta)} cues)")


if __name__ == "__main__":
    main()

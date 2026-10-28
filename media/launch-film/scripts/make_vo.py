"""Generate the EPI launch-film voiceover with Edge neural TTS (free, no key)."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "assets" / "audio"
AUDIO.mkdir(parents=True, exist_ok=True)

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "-6%"
PITCH = "-3Hz"

SEGMENTS = [
    (
        "vo1",
        "You already have immutable logs. CloudTrail integrity validation. "
        "Object Lock. But that only proves the record wasn't touched. "
        "Not that it's complete.",
    ),
    (
        "vo2",
        "EPI records the application layer. The prompt, the answer, "
        "the tool call, the policy decision. Hash chained, redacted, "
        "signed into one file.",
    ),
    (
        "vo3",
        "It answers three questions. Were the bytes altered. "
        "Is the signing key yours. Did the run follow policy. "
        "Change one byte, and the seal fails closed.",
    ),
    (
        "vo4",
        "The file is HTML and a ZIP. Open it in a browser, no account, "
        "no AWS console. Or witness only the hash, and keep the payload "
        "in your bucket.",
    ),
    (
        "vo5",
        "Don't argue with auditors. Hand them a file. Your immutable logs "
        "can stay where they are. Open source. M I T.",
    ),
]

FFMPEG = ROOT / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"
FFPROBE = ROOT / "node_modules" / "ffmpeg-static" / "ffprobe.exe"


def mp3_duration(path: Path) -> float:
    """Duration via ffmpeg decode (ffprobe is not shipped by ffmpeg-static)."""
    out = subprocess.run(
        [str(FFMPEG), "-hide_banner", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    for line in out.stderr.splitlines():
        if "time=" in line:
            stamp = line.split("time=")[1].split()[0]
            h, m, s = stamp.split(":")
            total = int(h) * 3600 + int(m) * 60 + float(s)
    return total


async def synth(name: str, text: str) -> None:
    out = AUDIO / f"{name}.mp3"
    comm = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await comm.save(str(out))
    print(f"{name}: {out.stat().st_size} bytes")


async def main() -> None:
    for name, text in SEGMENTS:
        await synth(name, text)

    meta = []
    for name, text in SEGMENTS:
        dur = mp3_duration(AUDIO / f"{name}.mp3")
        meta.append({"id": name, "text": text, "duration": round(dur, 3)})
        print(f"{name} duration {dur:.3f}s")

    (AUDIO / "vo.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())

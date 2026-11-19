#!/usr/bin/env python3
"""Render exact-text 16:9 frames for the EPI product walkthrough video.

Uses real CLI copy (not AI-garbled text). Output: website/assets/demo/frames/
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "frames"
W, H = 1920, 1080

# Palette — match product home (dark instrument)
BG = (11, 13, 16)
BG_PANEL = (20, 24, 32)
BG_TERM = (10, 12, 16)
INK = (242, 244, 247)
INK_SOFT = (200, 205, 214)
INK_MUTED = (139, 147, 161)
ACCENT = (61, 220, 151)
SIGNAL = (91, 140, 255)
WARN = (230, 184, 77)
BORDER = (42, 49, 64)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\CascadiaMono.ttf",
        r"C:\Windows\Fonts\CascadiaCode.ttf",
        r"C:\Windows\Fonts\lucon.ttf",
        r"C:\Windows\Fonts\seguiemj.ttf",
    ]
    if bold:
        candidates = [
            r"C:\Windows\Fonts\consolab.ttf",
            r"C:\Windows\Fonts\CascadiaMono.ttf",
        ] + candidates
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def sans(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    if bold:
        candidates = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ] + candidates
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box, r: int, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # subtle top gradient bar
    for y in range(0, 180):
        a = int(18 * (1 - y / 180))
        d.line([(0, y), (W, y)], fill=(BG[0] + a, BG[1] + a + 2, BG[2] + a + 4))
    # brand chip
    d.text((64, 36), "EPI LABS", font=sans(22, True), fill=ACCENT)
    d.text((180, 40), "· product walkthrough", font=sans(18), fill=INK_MUTED)
    return img, d


def draw_terminal(d: ImageDraw.ImageDraw, lines: list[tuple[str, tuple[int, int, int]]], title: str = "terminal — epi"):
    x0, y0, x1, y1 = 120, 120, W - 120, H - 100
    rounded(d, (x0, y0, x1, y1), 18, BG_TERM, BORDER, 2)
    # titlebar
    rounded(d, (x0, y0, x1, y0 + 48), 18, (16, 18, 24), None)
    d.rectangle((x0, y0 + 30, x1, y0 + 48), fill=(16, 18, 24))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((x0 + 22 + i * 28, y0 + 16, x0 + 38 + i * 28, y0 + 32), fill=c)
    d.text((x0 + 120, y0 + 14), title, font=font(18), fill=INK_MUTED)
    # body
    mono = font(28)
    y = y0 + 78
    for text, color in lines:
        d.text((x0 + 40, y), text, font=mono, fill=color)
        y += 42
        if y > y1 - 40:
            break


def frame_01_title() -> Image.Image:
    img, d = base()
    d.text((120, 280), "From pip install", font=sans(64, True), fill=INK)
    d.text((120, 370), "to a sealed .epi file", font=sans(64, True), fill=ACCENT)
    d.text(
        (120, 480),
        "Open-source evidence for AI agents — free offline forever.",
        font=sans(32),
        fill=INK_SOFT,
    )
    # file card mock
    rounded(d, (1200, 260, 1760, 720), 16, BG_PANEL, BORDER, 2)
    d.text((1240, 300), "demo_refund.epi", font=font(28, True), fill=INK)
    rounded(d, (1560, 300, 1720, 340), 8, ACCENT, None)
    d.text((1580, 308), "SEAL OK", font=sans(16, True), fill=(4, 18, 12))
    rows = [
        ("SHA-256", "a7b3…f21c"),
        ("Signature", "Ed25519 · valid"),
        ("Integrity", "PASS"),
        ("Mode", "Offline CLI"),
    ]
    y = 380
    for k, v in rows:
        d.text((1240, y), k, font=font(20), fill=INK_MUTED)
        d.text((1480, y), v, font=font(20), fill=ACCENT if "valid" in v or "PASS" in v else INK_SOFT)
        y += 48
    d.text((120, 920), "01 / 05  ·  install → record → seal → verify", font=sans(22), fill=INK_MUTED)
    return img


def frame_02_install() -> Image.Image:
    img, d = base()
    lines = [
        ("$ pip install epi-recorder", ACCENT),
        ("Collecting epi-recorder", INK_MUTED),
        ("  Downloading epi_recorder-4.4.0-py3-none-any.whl", INK_MUTED),
        ("Successfully installed epi-recorder-4.4.0", ACCENT),
        ("", INK),
        ("$ python -c \"import epi_recorder; print(epi_recorder.__version__)\"", INK_SOFT),
        ("4.4.0", ACCENT),
        ("", INK),
        ("# Apache-2.0 · works offline · no account required", INK_MUTED),
    ]
    draw_terminal(d, lines, "bash — install")
    d.text((120, 1000), "02 / 05  ·  get the package from PyPI", font=sans(22), fill=INK_MUTED)
    return img


def frame_03_record() -> Image.Image:
    img, d = base()
    lines = [
        ("# agent.py — wrap your run in record()", INK_MUTED),
        ("from epi_recorder import record", SIGNAL),
        ("", INK),
        ('with record("demo_refund.epi", workflow_name="refund"):', INK_SOFT),
        ('    session.log("agent.plan", goal="Refund ORD-9001")', INK_SOFT),
        ('    session.log("policy.check", result="ALLOW")', INK_SOFT),
        ('    session.log("agent.decision", decision="APPROVE")', INK_SOFT),
        ("", INK),
        ("$ python agent.py", ACCENT),
        ("[EPI] 4 steps → demo_refund.epi   Signed ✓", ACCENT),
        ("      Seal: signed · Next: epi view demo_refund.epi", INK_MUTED),
    ]
    draw_terminal(d, lines, "python — record & seal")
    d.text((120, 1000), "03 / 05  ·  every step hash-linked into one file", font=sans(22), fill=INK_MUTED)
    return img


def frame_04_verify() -> Image.Image:
    img, d = base()
    lines = [
        ("$ epi verify demo_refund.epi", ACCENT),
        ("", INK),
        ("  DECISION: PASS", ACCENT),
        ("  Integrity:    Verified", INK_SOFT),
        ("  Signature:    Valid (Ed25519)", INK_SOFT),
        ("  Notarized:    RFC 3161 (FreeTSA)", INK_SOFT),
        ("  Identity:     LOCAL · pin for org HIGH", WARN),
        ("", INK),
        ("  SEAL OK — signature valid. Identity is separate from seal.", INK_MUTED),
        ("", INK),
        ("$ ls -lh demo_refund.epi", ACCENT),
        ("-rw-r--r--  356K  demo_refund.epi   # portable evidence", INK_SOFT),
    ]
    draw_terminal(d, lines, "bash — verify")
    d.text((120, 1000), "04 / 05  ·  same bytes offline, in CI, for auditors", font=sans(22), fill=INK_MUTED)
    return img


def frame_05_viewer() -> Image.Image:
    img, d = base()
    # Prefer real product screenshot if present
    shot = ROOT / "docs" / "assets" / "epi-file-viewer-full.png"
    if shot.exists():
        viewer = Image.open(shot).convert("RGB")
        # fit into panel
        max_w, max_h = 1680, 780
        viewer.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        px = (W - viewer.width) // 2
        py = 140
        # shadow panel
        rounded(d, (px - 16, py - 16, px + viewer.width + 16, py + viewer.height + 16), 14, BG_PANEL, BORDER, 2)
        img.paste(viewer, (px, py))
        d.text((120, 1000), "05 / 05  ·  open the .epi in any browser — no dashboard login", font=sans(22), fill=INK_MUTED)
        d.text((120, 60), "epi view demo_refund.epi", font=font(24), fill=SIGNAL)
        return img

    lines = [
        ("$ epi view demo_refund.epi", ACCENT),
        ("Opening forensic viewer in browser…", INK_MUTED),
        ("", INK),
        ("  Signature: VALID", ACCENT),
        ("  Integrity: VERIFIED", ACCENT),
        ("  Timeline:  4 steps · decision trail intact", INK_SOFT),
        ("", INK),
        ("Or drop the file at https://epilabs.org/verify/", SIGNAL),
        ("  Private check = no upload", INK_MUTED),
    ]
    draw_terminal(d, lines, "viewer — browser")
    d.text((120, 1000), "05 / 05  ·  share the file, not a screenshot of logs", font=sans(22), fill=INK_MUTED)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = [
        ("01_title.png", frame_01_title),
        ("02_install.png", frame_02_install),
        ("03_record.png", frame_03_record),
        ("04_verify.png", frame_04_verify),
        ("05_viewer.png", frame_05_viewer),
    ]
    for name, fn in frames:
        path = OUT / name
        fn().save(path, "PNG", optimize=True)
        print("wrote", path, path.stat().st_size)


if __name__ == "__main__":
    main()

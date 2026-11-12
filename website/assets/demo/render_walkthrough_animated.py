#!/usr/bin/env python3
"""Animated product walkthrough — typewriter terminals, cursor blink, seal pulse.

Outputs frame sequences under website/assets/demo/anim/ then we ffmpeg to mp4.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "anim"
W, H = 1920, 1080
FPS = 30

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
DIM = (55, 62, 78)


def font(size: int, bold: bool = False):
    cands = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\CascadiaMono.ttf",
        r"C:\Windows\Fonts\lucon.ttf",
    ]
    if bold:
        cands = [r"C:\Windows\Fonts\consolab.ttf"] + cands
    for p in cands:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def sans(size: int, bold: bool = False):
    cands = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]
    if bold:
        cands = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"] + cands
    for p in cands:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


def blank():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(0, 200):
        a = int(22 * (1 - y / 200))
        d.line([(0, y), (W, y)], fill=(BG[0] + a, BG[1] + a + 2, BG[2] + a + 5))
    return img, d


def brand(d, step_label: str):
    d.text((64, 36), "EPI LABS", font=sans(22, True), fill=ACCENT)
    d.text((180, 40), "· product walkthrough", font=sans(18), fill=INK_MUTED)
    d.text((64, 1000), step_label, font=sans(22), fill=INK_MUTED)


def draw_terminal_chrome(d, title: str, progress: float = 1.0):
    x0, y0, x1, y1 = 100, 110, W - 100, H - 90
    # soft glow
    glow = int(40 * progress)
    if glow:
        d.rounded_rectangle(
            (x0 - 4, y0 - 4, x1 + 4, y1 + 4),
            radius=20,
            outline=(ACCENT[0] // 4, ACCENT[1] // 4, ACCENT[2] // 4),
            width=2,
        )
    d.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=BG_TERM, outline=BORDER, width=2)
    d.rounded_rectangle((x0, y0, x1, y0 + 48), radius=18, fill=(16, 18, 24))
    d.rectangle((x0, y0 + 28, x1, y0 + 48), fill=(16, 18, 24))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((x0 + 22 + i * 28, y0 + 16, x0 + 38 + i * 28, y0 + 32), fill=c)
    d.text((x0 + 120, y0 + 14), title, font=font(18), fill=INK_MUTED)
    # progress bar under titlebar
    bar_w = int((x1 - x0 - 40) * progress)
    d.rectangle((x0 + 20, y0 + 46, x0 + 20 + bar_w, y0 + 48), fill=ACCENT)
    return x0, y0, x1, y1


def typewriter_frames(
    title: str,
    lines: list[tuple[str, tuple]],
    step_label: str,
    prefix: str,
    chars_per_frame: float = 2.2,
    hold_after: int = 18,
    intro: int = 8,
):
    """Yield RGB frames with progressive typing + cursor blink."""
    # expand to char stream: list of (line_idx, visible_len) states
    total_chars = sum(len(t) for t, _ in lines) + len(lines) * 2
    frames_n = intro + int(total_chars / chars_per_frame) + hold_after
    # precompute cumulative
    line_lens = [len(t) for t, _ in lines]
    mono = font(28)

    for f in range(frames_n):
        img, d = blank()
        brand(d, step_label)
        # terminal entrance scale
        ent = ease_out(min(1.0, f / max(1, intro)))
        prog = min(1.0, max(0.0, (f - intro) / max(1, frames_n - intro - hold_after)))
        x0, y0, x1, y1 = draw_terminal_chrome(d, title, progress=0.15 + 0.85 * prog)

        # how many chars revealed after intro
        if f < intro:
            revealed = 0
        else:
            revealed = int((f - intro) * chars_per_frame)

        y = y0 + 78
        remaining = revealed
        active_line = 0
        for li, (text, color) in enumerate(lines):
            if remaining <= 0:
                # not yet started
                break
            take = min(len(text), remaining)
            shown = text[:take]
            d.text((x0 + 40, y), shown, font=mono, fill=color)
            remaining -= take
            active_line = li
            # if full line, consume newline pause
            if take >= len(text):
                remaining = max(0, remaining - 2)
            else:
                # cursor on this line
                bbox = d.textbbox((x0 + 40, y), shown, font=mono)
                cx = bbox[2] + 4
                if (f // 8) % 2 == 0:
                    d.rectangle((cx, y + 4, cx + 14, y + 30), fill=ACCENT)
                break
            y += 42
            if y > y1 - 50:
                break
        else:
            # all lines done — blinking cursor at end
            y_end = y0 + 78 + 42 * len(lines)
            if (f // 8) % 2 == 0 and f > intro:
                last = lines[-1][0] if lines else ""
                bbox = d.textbbox((x0 + 40, y_end - 42), last, font=mono)
                d.rectangle((bbox[2] + 4, y_end - 38, bbox[2] + 18, y_end - 12), fill=ACCENT)

        # subtle scanline
        for sy in range(y0 + 50, y1, 4):
            d.line([(x0 + 2, sy), (x1 - 2, sy)], fill=(14, 16, 20))

        path = OUT / f"{prefix}_{f:04d}.png"
        img.save(path, "PNG")
        yield path


def title_frames(n: int = 90):
    """Animated title + file card slide/pulse."""
    mono = font(20)
    for f in range(n):
        t = f / (n - 1)
        img, d = blank()
        brand(d, "01 / 05  ·  install → record → seal → verify")

        # title rise
        ty = int(lerp(340, 280, ease_out(min(1, t * 1.4))))
        alpha_t = ease_out(min(1, t * 2.2))
        # simulate alpha by blend with bg
        def fade_color(c, a):
            return tuple(int(BG[i] + (c[i] - BG[i]) * a) for i in range(3))

        d.text((120, ty), "From pip install", font=sans(64, True), fill=fade_color(INK, alpha_t))
        d.text(
            (120, ty + 90),
            "to a sealed .epi file",
            font=sans(64, True),
            fill=fade_color(ACCENT, ease_out(min(1, max(0, t * 2.0 - 0.15)))),
        )
        d.text(
            (120, ty + 200),
            "Open-source evidence for AI agents — free offline forever.",
            font=sans(30),
            fill=fade_color(INK_SOFT, ease_out(min(1, max(0, t * 1.8 - 0.25)))),
        )

        # card slide from right
        slide = ease_out(min(1, max(0, t * 1.5 - 0.2)))
        cx = int(lerp(2000, 1200, slide))
        cy = 250
        # pulse glow
        pulse = 0.5 + 0.5 * abs(((f % 40) / 20) - 1)
        glow = int(30 + 40 * pulse * slide)
        d.rounded_rectangle(
            (cx - 6, cy - 6, cx + 560 + 6, cy + 460 + 6),
            radius=20,
            outline=(ACCENT[0] * glow // 255, ACCENT[1] * glow // 255, ACCENT[2] * glow // 255),
            width=2,
        )
        d.rounded_rectangle((cx, cy, cx + 560, cy + 460), radius=16, fill=BG_PANEL, outline=BORDER, width=2)
        d.text((cx + 40, cy + 36), "demo_refund.epi", font=font(28, True), fill=INK)

        # seal pill pulse
        pill_a = ease_out(min(1, max(0, t * 2 - 0.5)))
        pw = 150
        px0 = cx + 360
        py0 = cy + 36
        pill_col = tuple(int(lerp(BG_PANEL[i], ACCENT[i], pill_a)) for i in range(3))
        d.rounded_rectangle((px0, py0, px0 + pw, py0 + 36), radius=8, fill=pill_col)
        if pill_a > 0.4:
            d.text((px0 + 22, py0 + 8), "SEAL OK", font=sans(16, True), fill=(4, 18, 12))

        rows = [
            ("SHA-256", "a7b3…f21c", INK_SOFT),
            ("Signature", "Ed25519 · valid", ACCENT),
            ("Integrity", "PASS", ACCENT),
            ("Mode", "Offline CLI", INK_SOFT),
        ]
        ry = cy + 120
        for i, (k, v, col) in enumerate(rows):
            ra = ease_out(min(1, max(0, t * 2.2 - 0.45 - i * 0.08)))
            d.text((cx + 40, ry), k, font=mono, fill=fade_color(INK_MUTED, ra))
            d.text((cx + 240, ry), v, font=mono, fill=fade_color(col, ra))
            ry += 52

        # bottom progress dots
        for i in range(5):
            dx = 120 + i * 28
            on = i == 0
            d.ellipse((dx, 1040, dx + 12, 1052), fill=ACCENT if on else DIM)

        path = OUT / f"01_{f:04d}.png"
        img.save(path, "PNG")
        yield path


def verify_success_pulse(lines, step_label, prefix, n_hold=50):
    """Show full terminal then pulse DECISION PASS."""
    # first typewrite quickly then hold with pulse
    frames = list(
        typewriter_frames(
            "bash — verify",
            lines,
            step_label,
            prefix + "t",
            chars_per_frame=4.5,
            hold_after=4,
            intro=6,
        )
    )
    # re-render hold frames with green flash on PASS line
    mono = font(28)
    for f in range(n_hold):
        img, d = blank()
        brand(d, step_label)
        x0, y0, x1, y1 = draw_terminal_chrome(d, "bash — verify", progress=1.0)
        y = y0 + 78
        pulse = 0.55 + 0.45 * abs(((f % 24) / 12) - 1)
        for text, color in lines:
            col = color
            if "DECISION: PASS" in text:
                col = tuple(int(lerp(color[i], 255, 0.15 * pulse)) for i in range(3))
                # highlight bar
                d.rounded_rectangle(
                    (x0 + 28, y - 4, x0 + 520, y + 36),
                    radius=6,
                    fill=(int(20 * pulse), int(40 + 30 * pulse), int(28 * pulse)),
                )
            d.text((x0 + 40, y), text, font=mono, fill=col)
            y += 42
        path = OUT / f"{prefix}_{f:04d}.png"
        img.save(path, "PNG")
        frames.append(path)
        yield path


def viewer_kenburns(n: int = 75):
    shot = ROOT / "docs" / "assets" / "epi-file-viewer-full.png"
    if not shot.exists():
        for p in typewriter_frames(
            "viewer",
            [("$ epi view demo_refund.epi", ACCENT), ("Opening browser…", INK_MUTED)],
            "05 / 05  ·  browser view",
            "05",
            hold_after=40,
        ):
            yield p
        return

    src = Image.open(shot).convert("RGB")
    tw, th = src.size
    crop_h = min(th, int(tw * 9 / 16))
    base_crop = src.crop((0, 0, tw, crop_h))

    for f in range(n):
        t = f / (n - 1)
        img, d = blank()
        brand(d, "05 / 05  ·  open the .epi in any browser — no dashboard login")
        d.text((64, 70), "epi view demo_refund.epi", font=font(24), fill=SIGNAL)

        # ken burns: zoom 1.0 -> 1.12, slight pan
        scale = 1.0 + 0.12 * ease_in_out(t)
        bw, bh = 1600, 780
        # scale base_crop
        nw, nh = int(base_crop.width * scale), int(base_crop.height * scale)
        scaled = base_crop.resize((nw, nh), Image.Resampling.LANCZOS)
        # pan down slowly into the PASSED section
        max_y = max(0, nh - bh)
        oy = int(max_y * ease_in_out(t) * 0.55)
        max_x = max(0, nw - bw)
        ox = int(max_x * 0.35 * (1 - t))
        view = scaled.crop((ox, oy, ox + min(bw, nw - ox), oy + min(bh, nh - oy)))
        view.thumbnail((1680, 780), Image.Resampling.LANCZOS)

        px = (W - view.width) // 2
        py = 150
        # entrance
        ent = ease_out(min(1, t * 3))
        # shadow panel
        d.rounded_rectangle(
            (px - 16, py - 16, px + view.width + 16, py + view.height + 16),
            radius=14,
            fill=BG_PANEL,
            outline=BORDER,
            width=2,
        )
        if ent < 1:
            # fade by darkening
            darkened = ImageEnhance.Brightness(view).enhance(0.35 + 0.65 * ent)
            img.paste(darkened, (px, py))
        else:
            img.paste(view, (px, py))

        # floating badge
        if t > 0.25:
            ba = ease_out(min(1, (t - 0.25) * 3))
            bx, by = px + view.width - 180, py + 20
            d.rounded_rectangle((bx, by, bx + 150, by + 40), radius=8, fill=ACCENT)
            d.text((bx + 28, by + 10), "PASSED", font=sans(18, True), fill=(4, 18, 12))

        # progress dots
        for i in range(5):
            dx = 120 + i * 28
            d.ellipse((dx, 1040, dx + 12, 1052), fill=ACCENT if i == 4 else DIM)

        path = OUT / f"05_{f:04d}.png"
        img.save(path, "PNG")
        yield path


def main():
    if OUT.exists():
        for p in OUT.glob("*.png"):
            p.unlink()
    OUT.mkdir(parents=True, exist_ok=True)

    seq: list[Path] = []

    print("01 title…")
    seq.extend(title_frames(75))  # 2.5s

    print("02 install typewriter…")
    seq.extend(
        typewriter_frames(
            "bash — install",
            [
                ("$ pip install epi-recorder", ACCENT),
                ("Collecting epi-recorder", INK_MUTED),
                ("  Downloading epi_recorder-4.4.0-py3-none-any.whl", INK_MUTED),
                ("Successfully installed epi-recorder-4.4.0", ACCENT),
                ("", INK),
                ('$ python -c "import epi_recorder; print(epi_recorder.__version__)"', INK_SOFT),
                ("4.4.0", ACCENT),
                ("", INK),
                ("# Apache-2.0 · offline · no account required", INK_MUTED),
            ],
            "02 / 05  ·  get the package from PyPI",
            "02",
            chars_per_frame=2.8,
            hold_after=22,
            intro=10,
        )
    )

    print("03 record typewriter…")
    seq.extend(
        typewriter_frames(
            "python — record & seal",
            [
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
            ],
            "03 / 05  ·  every step hash-linked into one file",
            "03",
            chars_per_frame=3.0,
            hold_after=24,
            intro=8,
        )
    )

    print("04 verify typewriter + pulse…")
    seq.extend(
        typewriter_frames(
            "bash — verify",
            [
                ("$ epi verify demo_refund.epi", ACCENT),
                ("", INK),
                ("  DECISION: PASS", ACCENT),
                ("  Integrity:    Verified", INK_SOFT),
                ("  Signature:    Valid (Ed25519)", INK_SOFT),
                ("  Notarized:    RFC 3161 (FreeTSA)", INK_SOFT),
                ("  Identity:     LOCAL · pin for org HIGH", WARN),
                ("", INK),
                ("  SEAL OK — signature valid. Identity ≠ seal.", INK_MUTED),
                ("", INK),
                ("$ ls -lh demo_refund.epi", ACCENT),
                ("-rw-r--r--  356K  demo_refund.epi", INK_SOFT),
            ],
            "04 / 05  ·  same bytes offline, in CI, for auditors",
            "04",
            chars_per_frame=3.2,
            hold_after=28,
            intro=8,
        )
    )

    print("05 viewer ken burns…")
    seq.extend(viewer_kenburns(80))

    # write concat list for ffmpeg
    list_path = OUT / "frames.txt"
    with list_path.open("w", encoding="utf-8") as fh:
        for p in seq:
            # duration per frame
            fh.write(f"file '{p.resolve().as_posix()}'\n")
            fh.write(f"duration {1/FPS:.6f}\n")
        # last frame needs a repeat for concat demuxer
        if seq:
            fh.write(f"file '{seq[-1].resolve().as_posix()}'\n")

    print(f"frames: {len(seq)}  (~{len(seq)/FPS:.1f}s)  list: {list_path}")
    return list_path, len(seq)


if __name__ == "__main__":
    main()

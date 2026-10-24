"""
Build the EPI launch film's complete audio bed, deterministically, with numpy.

Output: assets/audio/score.wav  (48 kHz, stereo, 16-bit)

The film has a voiceover already recorded as vo1..vo5.mp3. This script
synthesises the music, sound design and ducking, then mixes the voiceover in
at the measured scene offsets, and masters the result. No sampled or licensed
audio is used: every sound here is generated from oscillators and noise.

Scene timings live in SCENES and must match the labels in index.html.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "assets" / "audio"
FFMPEG = ROOT / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"

SR = 48_000

# --- picture timeline (single source of truth; mirror in index.html) -------
SCENES = {"s1": 0.0, "s2": 11.8, "s3": 23.9, "s4": 36.7, "s5": 49.7}
DURS = {"s1": 11.8, "s2": 12.1, "s3": 12.8, "s4": 13.0, "s5": 10.5}
TOTAL = 60.2
TAMPER = SCENES["s3"] + 8.15  # the single byte that breaks the seal

N = int(TOTAL * SR)
RNG = np.random.default_rng(20261024)

# Voiceover placement, in seconds. Each line starts just after its scene lands.
VO_AT = {
    "vo1": SCENES["s1"] + 0.8,
    "vo2": SCENES["s2"] + 0.6,
    "vo3": SCENES["s3"] + 0.5,
    "vo4": SCENES["s4"] + 0.4,
    "vo5": SCENES["s5"] + 0.8,
}

# One chord every six seconds, 80 BPM, four beats to the bar.
PROGRESSION = ["Am", "F", "C", "G"]
CHORDS = [(float(i * 6), PROGRESSION[i % 4]) for i in range(int(TOTAL // 6) + 1)]

NOTE = {
    "A2": 110.00,
    "B2": 123.47,
    "C3": 130.81,
    "D3": 146.83,
    "E3": 164.81,
    "F2": 87.31,
    "G2": 98.00,
    "G3": 196.00,
}
CHORD_NOTES = {
    "Am": ["A2", "C3", "E3"],
    "F": ["F2", "A2", "C3"],
    "C": ["C3", "E3", "G3"],
    "G": ["G2", "B2", "D3"],
}


# --------------------------------------------------------------------------
# small signal helpers
# --------------------------------------------------------------------------
def buf() -> np.ndarray:
    return np.zeros((N, 2), dtype=np.float64)


def lowpass(x: np.ndarray, fc: float, order: int = 4) -> np.ndarray:
    """Zero-phase low-pass via FFT magnitude shaping."""
    if x.ndim > 1:
        return np.stack([lowpass(x[:, c], fc, order) for c in range(x.shape[1])], axis=1)
    n = len(x)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    spec /= 1.0 + (f / fc) ** order
    return np.fft.irfft(spec, n)


def highpass(x: np.ndarray, fc: float, order: int = 4) -> np.ndarray:
    if x.ndim > 1:
        return np.stack([highpass(x[:, c], fc, order) for c in range(x.shape[1])], axis=1)
    n = len(x)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    spec *= 1.0 - 1.0 / (1.0 + (f / fc) ** order)
    return np.fft.irfft(spec, n)


def place(target: np.ndarray, clip: np.ndarray, at: float, gain: float = 1.0) -> None:
    """Add a mono or stereo clip into the stereo master at time `at`."""
    start = int(round(at * SR))
    if clip.ndim == 1:
        clip = np.stack([clip, clip], axis=1)
    if start < 0:
        clip = clip[-start:]
        start = 0
    if start >= N or len(clip) == 0:
        return
    end = min(N, start + len(clip))
    target[start:end] += clip[: end - start] * gain


def env_ar(n: int, attack: float, release: float, curve: float = 2.0) -> np.ndarray:
    """Attack/release envelope over n samples."""
    e = np.ones(n, dtype=np.float64)
    a = min(n, max(1, int(attack * SR)))
    r = min(n, max(1, int(release * SR)))
    e[:a] = np.linspace(0.0, 1.0, a) ** curve
    e[n - r :] *= np.linspace(1.0, 0.0, r) ** curve
    return e


def box_smooth(x: np.ndarray, win: int) -> np.ndarray:
    """Centred moving average in O(n), same length as x.

    np.convolve with a 5k-sample boxcar is O(n*m) and takes minutes on a
    60 s stereo bed; the cumulative-sum form is linear.
    """
    if win <= 1:
        return x.copy()
    c = np.cumsum(np.concatenate(([0.0], x)))
    sm = (c[win:] - c[:-win]) / win
    pad_l = (win - 1) // 2
    pad_r = win - 1 - pad_l
    return np.concatenate((np.full(pad_l, sm[0]), sm, np.full(pad_r, sm[-1])))


def tone(freq: float, dur: float, harmonics=((1, 1.0), (2, 0.3), (3, 0.1)), detune=0.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float64)
    for mult, amp in harmonics:
        out += amp * np.sin(2 * np.pi * freq * mult * (1.0 + detune) * t)
    return out


def reverb(x: np.ndarray, decay: float = 0.55, size: float = 2.4, mix: float = 0.35) -> np.ndarray:
    """Cheap convolution reverb with a synthetic, deterministic impulse."""
    n_ir = int(size * SR)
    t = np.arange(n_ir) / SR
    ir = RNG.standard_normal(n_ir) * np.exp(-t / decay)
    ir = lowpass(ir, 4200.0, 2)
    ir[: int(0.012 * SR)] = 0.0
    ir /= np.max(np.abs(ir)) or 1.0

    if x.ndim == 1:
        return _convolve_reverb(x, ir, mix)

    return np.stack([_convolve_reverb(x[:, c], ir, mix) for c in range(x.shape[1])], axis=1)


def _convolve_reverb(x: np.ndarray, ir: np.ndarray, mix: float) -> np.ndarray:
    n = len(x) + len(ir)
    nfft = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x)]
    scale = np.max(np.abs(x)) or 1.0
    wet_peak = np.max(np.abs(wet)) or 1.0
    wet = wet / wet_peak * scale
    return x * (1.0 - mix) + wet * mix


# --------------------------------------------------------------------------
# instruments
# --------------------------------------------------------------------------
def build_pad() -> np.ndarray:
    """Sustained, slowly breathing chord bed."""
    out = buf()
    for i, (start, name) in enumerate(CHORDS):
        end = CHORDS[i + 1][0] if i + 1 < len(CHORDS) else TOTAL
        dur = (end - start) + 1.8
        n = int(dur * SR)
        env = env_ar(n, attack=1.4 if i else 2.4, release=1.8, curve=1.6)

        left = np.zeros(n, dtype=np.float64)
        right = np.zeros(n, dtype=np.float64)
        for note_i, note_name in enumerate(CHORD_NOTES[name]):
            f = NOTE[note_name]
            amp = 0.85 if note_i == 0 else 0.6
            left += tone(f, dur, detune=+0.0016) * amp
            right += tone(f, dur, detune=-0.0016) * amp

        # one octave below the root, for weight
        f_root = NOTE[CHORD_NOTES[name][0]]
        left += tone(f_root * 0.5, dur, harmonics=((1, 1.0), (2, 0.15))) * 0.5
        right += tone(f_root * 0.5, dur, harmonics=((1, 1.0), (2, 0.15))) * 0.5

        # slow amplitude breathing
        t = np.arange(n) / SR
        breathe = 1.0 + 0.12 * np.sin(2 * np.pi * 0.075 * t + note_i * 1.7)
        pad = np.stack([left, right], axis=1) * (env * breathe)[:, None]
        pad = np.stack(
            [lowpass(pad[:, 0], 2600.0, 2), lowpass(pad[:, 1], 2600.0, 2)], axis=1
        )
        peak = np.max(np.abs(pad)) or 1.0
        place(out, pad / peak, start - 0.9, 1.0)

    return reverb(out, decay=0.9, size=3.0, mix=0.42)


def build_pulse() -> np.ndarray:
    """Quiet eighth-note pulse that starts with act two."""
    out = buf()
    step = 60.0 / 80.0 / 2.0  # eighth note at 80 BPM
    t = SCENES["s2"]
    while t < TOTAL - 1.0:
        # mute through the tamper beat so the failure lands in silence
        if not (TAMPER - 1.1 <= t <= TAMPER + 0.9):
            n = int(0.09 * SR)
            tt = np.arange(n) / SR
            body = np.sin(2 * np.pi * 2600.0 * tt) * np.exp(-tt / 0.010)
            air = lowpass(RNG.standard_normal(n), 7000.0, 2) * np.exp(-tt / 0.006)
            click = body * 0.5 + air * 0.5
            click *= env_ar(n, 0.001, 0.02)
            accent = 1.0 if abs((t / step) % 4.0) < 0.01 else 0.55
            place(out, click, t, 0.055 * accent)
        t += step
    return out


def build_kick() -> np.ndarray:
    """Low, soft heartbeat on the bar line once the verification act starts."""
    out = buf()
    t = SCENES["s3"]
    while t < TOTAL - 1.0:
        n = int(0.55 * SR)
        tt = np.arange(n) / SR
        freq = 48.0 + 62.0 * np.exp(-tt / 0.045)
        phase = 2 * np.pi * np.cumsum(freq) / SR
        body = np.sin(phase) * np.exp(-tt / 0.16)
        place(out, body * env_ar(n, 0.004, 0.08), t, 0.30)
        t += 3.0
    return out


def build_riser() -> np.ndarray:
    """Tension sweep into the tampered byte."""
    dur = 3.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    sweep_f = 180.0 * (10.0 ** (t / dur))  # 180 Hz -> 1.8 kHz
    sweep = np.sin(2 * np.pi * np.cumsum(sweep_f) / SR)
    air = lowpass(RNG.standard_normal(n), 3000.0, 1) * 0.5
    ramp = (t / dur) ** 2.2
    body = (sweep * 0.45 + air * 0.55) * ramp
    return body * env_ar(n, 0.05, 0.02)


def build_impact() -> np.ndarray:
    n = int(1.1 * SR)
    tt = np.arange(n) / SR
    freq = 44.0 + 70.0 * np.exp(-tt / 0.05)
    sub = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-tt / 0.26)
    crack = lowpass(RNG.standard_normal(n), 1800.0, 2) * np.exp(-tt / 0.03)
    return (sub * 0.85 + crack * 0.35) * env_ar(n, 0.002, 0.05)


def build_chime() -> np.ndarray:
    """Closing resolution bell."""
    dur = 3.2
    n = int(dur * SR)
    tt = np.arange(n) / SR
    body = (
        np.sin(2 * np.pi * 523.25 * tt) * 1.0
        + np.sin(2 * np.pi * 1046.5 * tt) * 0.35
        + np.sin(2 * np.pi * 1567.98 * tt) * 0.14
    )
    body *= np.exp(-tt / 0.9) * env_ar(n, 0.008, 0.4)
    return reverb(body, decay=0.6, size=2.6, mix=0.5)


def build_sfx() -> np.ndarray:
    """Sparse UI ticks on the moments that matter, keyed to the scene grid."""
    out = buf()
    marks = [
        ("s1", 1.15, 0.20),   # immutable-log card lands
        ("s1", 5.20, 0.22),   # "not recorded" card lands
        ("s1", 7.00, 0.18),   # rule
        ("s2", 0.80, 0.16),   # code card
        ("s2", 1.30, 0.14),   # nodes 1-6
        ("s2", 1.82, 0.14),
        ("s2", 2.34, 0.14),
        ("s2", 2.86, 0.14),
        ("s2", 3.38, 0.14),
        ("s2", 3.90, 0.14),
        ("s2", 5.90, 0.20),   # seal chip
        ("s3", 3.20, 0.18),   # pills
        ("s3", 3.80, 0.18),
        ("s3", 4.40, 0.18),
        ("s3", 6.80, 0.16),   # hex panel
        ("s3", 8.55, 0.30),   # stamp
        ("s4", 0.80, 0.16),   # viewer.html
        ("s4", 1.05, 0.16),   # payload.zip
        ("s4", 2.10, 0.20),   # witness card
        ("s4", 2.40, 0.20),   # browser
        ("s4", 4.40, 0.22),   # receipt
        ("s4", 7.00, 0.16),   # receipt border
        ("s4", 9.60, 0.16),   # row highlight
        ("s5", 4.00, 0.18),   # install pill
    ]
    for scene, offset, gain in marks:
        at = SCENES[scene] + offset
        n = int(0.12 * SR)
        tt = np.arange(n) / SR
        tick = np.sin(2 * np.pi * 1450.0 * tt) * np.exp(-tt / 0.012)
        tick += lowpass(RNG.standard_normal(n), 9000.0, 2) * np.exp(-tt / 0.005) * 0.4
        place(out, tick * env_ar(n, 0.001, 0.02), at, gain * 0.16)
    return out


# --------------------------------------------------------------------------
# voiceover
# --------------------------------------------------------------------------
def load_vo(name: str) -> np.ndarray:
    """Decode a VO mp3 to a 48 kHz mono float array via ffmpeg."""
    src = AUDIO / f"{name}.mp3"
    dst = AUDIO / f".{name}.tmp.wav"
    subprocess.run(
        [str(FFMPEG), "-y", "-loglevel", "error", "-i", str(src), "-ar", str(SR), "-ac", "1", str(dst)],
        check=True,
    )
    with wave.open(str(dst), "rb") as w:
        raw = w.readframes(w.getnframes())
    dst.unlink(missing_ok=True)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    return data


def build_vo() -> tuple[np.ndarray, np.ndarray]:
    """Return the placed voiceover and a smooth ducking envelope."""
    out = buf()
    for name, at in VO_AT.items():
        mono = load_vo(name)
        peak = np.max(np.abs(mono)) or 1.0
        mono = mono / peak * 0.82
        # gentle de-esser-ish soften of the very top, plus a touch of room
        mono = lowpass(mono, 11_000.0, 2)
        mono = reverb(mono, decay=0.28, size=1.1, mix=0.10)
        place(out, mono, at, 1.0)

    # ducking envelope: 1 where the voice is present, 0 where it is not
    energy = np.max(np.abs(out), axis=1)
    win = int(0.12 * SR)
    smooth = box_smooth(energy, win)
    smooth = box_smooth(smooth, win)
    env = np.clip(smooth / (np.max(smooth) * 0.10), 0.0, 1.0)
    env = box_smooth(env, int(0.25 * SR))
    return out, env


# --------------------------------------------------------------------------
# mix
# --------------------------------------------------------------------------
def main() -> None:
    print("building pad…")
    pad = build_pad()
    print("building pulse, kick, riser, impact, chime, sfx…")
    pulse = build_pulse()
    kick = build_kick()
    riser = build_riser()
    impact = build_impact()
    chime = build_chime()
    sfx = build_sfx()
    print("placing voiceover…")
    vo, duck = build_vo()

    music = pad * 0.30 + pulse * 0.55 + kick * 0.55
    duck_gain = (1.0 - 0.62 * duck)[:, None]
    music = music * duck_gain

    # The tamper beat: everything drops out for 1.1 s, then the impact lands.
    drop_a, drop_b = int((TAMPER - 1.1) * SR), int(TAMPER * SR)
    music[drop_a:drop_b] *= np.linspace(1.0, 0.0, drop_b - drop_a)[:, None] ** 1.5

    master = buf()
    master += music
    master += sfx * 0.9
    place(master, riser, TAMPER - 3.0, 0.16)
    place(master, impact, TAMPER, 0.55)
    place(master, chime, SCENES["s5"] + 6.1, 0.22)
    master += vo * 0.92

    # scene-change air: a very quiet swell at each act boundary
    for at in (SCENES["s2"], SCENES["s3"], SCENES["s4"], SCENES["s5"]):
        n = int(1.4 * SR)
        tt = np.arange(n) / SR
        swell = lowpass(RNG.standard_normal(n), 900.0, 2) * np.sin(np.pi * tt / 1.4) ** 2
        place(master, swell, at - 0.5, 0.020)

    # master bus: gentle soft clip, then peak normalise to -1 dBFS
    master = lowpass(master, 16_000.0, 2)
    peak = np.max(np.abs(master))
    master = master / peak * 1.25
    master = np.tanh(master) * 0.94
    master *= 0.89 / max(np.max(np.abs(master)), 1e-9)

    # 30 ms fade in / 1.4 s fade out so the film opens and closes cleanly
    fi = int(0.03 * SR)
    master[:fi] *= np.linspace(0.0, 1.0, fi)[:, None]
    fo = int(1.4 * SR)
    master[-fo:] *= np.linspace(1.0, 0.0, fo)[:, None] ** 1.5

    out_path = AUDIO / "score.wav"
    pcm = np.clip(master, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    rms = np.sqrt(np.mean(master**2))
    print(f"wrote {out_path}  {out_path.stat().st_size / 1e6:.1f} MB")
    print(f"duration {len(master) / SR:.2f}s  peak {np.max(np.abs(master)):.3f}  rms {20 * np.log10(rms):.1f} dBFS")
    print("VO at: " + ", ".join(f"{k}={v:.2f}" for k, v in VO_AT.items()))


if __name__ == "__main__":
    main()

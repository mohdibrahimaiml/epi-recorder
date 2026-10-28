# EPI launch film — source

The 60-second film on [epilabs.org](https://epilabs.org) (the "Why EPI exists" section).
The rendered output lives in [`website/assets/`](../../website/assets/):

| Output | File |
|---|---|
| Film (1920×1080, 30 fps, 60.2 s, H.264 + AAC) | `epi-walkthrough.mp4` |
| Poster (frame at 9.8 s) | `epi-walkthrough-poster.jpg` |
| Social card (1200×630) | `epi-walkthrough-og.jpg` |
| Captions (sentence-level WebVTT) | `epi-launch.vtt` |

This folder is the editable source, kept out of the site build: `website/` only
ships the rendered files.

## What is here

```
index.html            the HyperFrames composition (scenes, timeline, copy)
hyperframes.json      project config
meta.json             composition id/name
scripts/make_vo.py    regenerates the voiceover with edge-tts (free, no key)
scripts/make_score.py synthesises music/SFX and mixes the VO (numpy)
scripts/make_captions.py  builds the WebVTT from vo.json + VO_AT
assets/audio/vo*.mp3  recorded voiceover segments (10.6–12.2 s each)
assets/audio/vo.json  the VO script + measured durations
assets/fonts/         Inter, Instrument Serif, JetBrains Mono (woff2)
assets/gsap.min.js    animation runtime
assets/logo-*.png     brand marks used in the close
```

Not committed (generated): `node_modules/`, `renders/`, `.frames/`,
`.hyperframes/`, `assets/audio/score.wav` — the score is ~11 MB and is
reproducible byte-for-byte from `make_score.py`.

## Rebuild

Requirements: Python 3.11+, Node 20+, and network access for the TTS step.

```bash
cd media/launch-film
pip install numpy edge-tts
npm install                     # ffmpeg-static / ffprobe-static

python scripts/make_vo.py       # writes vo*.mp3 + vo.json, prints durations
python scripts/make_score.py    # writes assets/audio/score.wav (60.2 s)
python scripts/make_captions.py # writes assets/audio/epi-launch.vtt

npx hyperframes render --quality looks --output ../../website/assets/epi-walkthrough.mp4
cp assets/audio/epi-launch.vtt ../../website/assets/
```

Poster and OG card (frame 9.8 s):

```bash
ffmpeg -y -ss 9.8 -i ../../website/assets/epi-walkthrough.mp4 -frames:v 1 -q:v 4 \
  ../../website/assets/epi-walkthrough-poster.jpg
ffmpeg -y -ss 9.8 -i ../../website/assets/epi-walkthrough.mp4 -frames:v 1 \
  -vf "scale=1200:-1,crop=1200:630" -q:v 3 ../../website/assets/epi-walkthrough-og.jpg
```

## Timing contract

Scene starts live in two places that must agree:

- `index.html` → `var S = { s1, s2, s3, s4, s5, end }` and the GSAP labels
- `scripts/make_score.py` → `SCENES`, `DURS`, `TOTAL`, `VO_AT`

Current: `0 / 11.8 / 23.9 / 36.7 / 49.7`, total **60.2 s**. Change one, change
the other, then re-run the score and the render.

## Notes

- The voice is `en-US-AndrewMultilingualNeural` via edge-tts at `rate=-6%`,
  `pitch=-3Hz`; `vo.json` stores the exact text next to each measured duration.
- The score is synthesised, not sampled: every sound is oscillators + noise, so
  the film carries no third-party audio licence.
- Fonts are bundled only so a render is reproducible offline. They are OFL
  (Inter, JetBrains Mono) and the Instrument Serif licence; do not redistribute
  them outside the repo.

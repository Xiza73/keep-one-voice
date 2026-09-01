# Fixtures

Short audio clips for tests and manual verification. Keep them under a few
seconds. Never commit large or copyrighted audio.

## tone.mp3

A two second 440 Hz sine, stereo at 44.1 kHz. Deliberately *not* mono 16 kHz, so
running it through `kov` proves the decode stage really converts. Regenerate it
with:

```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=2" -ac 2 -ar 44100 -y fixtures/tone.mp3
```

A sine tone is enough to smoke-test F0. It is **not** enough to judge cleaning
quality: F1 onwards needs real speech with real noise, measured with SI-SDR and
PESQ rather than by ear.

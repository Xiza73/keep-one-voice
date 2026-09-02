# Changelog

Notable changes to this project, newest first.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-09-02

First release. `kov` takes an audio file and returns a clean track with one
voice: the main one.

[Download](https://github.com/Xiza73/keep-one-voice/releases/tag/v0.1.0)
(macOS, Apple Silicon).

### Added

- **CLI** — `kov <input> -o <output>`, with `--stages` to select what runs and
  `--transcript` to write out what was said. Errors say what to do about them:
  a missing FFmpeg names the install command, a gated model names the licence
  page and the environment variable.
- **Decoding** — any container FFmpeg understands becomes mono 48 kHz PCM. The
  input is probed and length-checked before decoding, and paths are resolved so
  a file named `-y` cannot arrive as a flag.
- **Denoising** with DeepFilterNet 3 — measured at **+11.8 dB** SI-SDR on
  broadband noise.
- **Source separation** with Demucs v4, keeping the vocals stem. It turned out
  to matter most for low-frequency noise rather than for music: **+11.2 dB** on
  traffic-like rumble, where denoising alone managed +4.1 dB.
- **Diarization** with pyannote 3.1, behind its manual licence gate.
- **Speaker extraction** — model-free masking, with ramped edges so a turn
  boundary is not a click.
- **Transcription** with faster-whisper, off by default. The language is
  detected, not configured.
- **Measurement harness** — `bun run fixtures` builds a seeded corpus of 48
  single-voice mixtures and 5 multi-speaker conversations; `bun run eval` scores
  it with SI-SDR. The corpus regenerates byte-identical, so numbers are
  comparable across runs.

### Known limitations

Documented because they are real, not because they are theoretical.

- **Diarization has never been measured.** `pyannote/speaker-diarization-3.1` is
  gated and no token was available during development, so it has not run against
  the corpus. This is why the release is 0.1.0 and not 1.0.0.
- **Extraction is turn masking, not target-speaker separation.** Where two
  people talk at once, both are kept.
- **The dominant-speaker heuristic can aim at the wrong voice** when the other
  person talks longer or was closer to the microphone.
- **The test corpus is synthetic.** It compares models against each other; it
  does not say how the result sounds on a real recording.
- **Only a macOS arm64 binary is published**, because it is the only one that
  was run and verified. Other platforms build from source with one command.

[Unreleased]: https://github.com/Xiza73/keep-one-voice/compare/v0.1.0...dev
[0.1.0]: https://github.com/Xiza73/keep-one-voice/releases/tag/v0.1.0

"""Reproducible test corpus generation.

Real recordings cannot be measured: there is no clean reference to compare
against, so SI-SDR is undefined. This module builds the opposite — speech
synthesised locally, noise generated from a seed, and mixtures at exact SNRs —
so every file in the corpus comes with the ground truth that produced it.

A synthetic corpus is enough to answer "did this denoiser help, and by how many
decibels". It is not enough to answer "does this sound good to a person". Both
questions matter; only the first one belongs in an automated gate.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from kov_worker.conversations import SCENARIOS, dominant_speaker, plan_turns, render
from kov_worker.metrics import mix_at_snr

# Long enough that a diarizer has something to latch onto in each turn.
CONVERSATION_TURN_MS = 1_500

NOISE_KINDS: tuple[str, ...] = ("white", "brown", "hum", "music")

# A plain I-vi-IV-V loop with a bass line and a beat. Synthetic on purpose:
# nothing in this repository may carry someone else's copyright, and a seeded
# generator keeps the corpus reproducible. It is a weaker test than real music,
# which Demucs was trained on — see fixtures/README.md.
MUSIC_ROOT_HZ = 110.0
MUSIC_TEMPO_BPM = 96.0
MUSIC_PROGRESSION: tuple[tuple[int, ...], ...] = ((0, 4, 7), (9, 12, 16), (5, 9, 12), (7, 11, 14))

DEFAULT_SNR_LEVELS: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)

# Matches the pipeline rate. DeepFilterNet3 runs at 48 kHz, and decoding to a
# lower rate first would destroy the band it is meant to work on.
DEFAULT_SAMPLE_RATE = 48_000

MAINS_HZ = 50.0

PEAK = 0.9


class FixtureError(RuntimeError):
    """Raised when the corpus cannot be produced."""


@dataclass(frozen=True)
class Speaker:
    key: str
    voice: str
    text: str


@dataclass(frozen=True)
class CorpusEntry:
    speaker: str
    noise: str
    snr_db: float
    clean: str
    noisy: str


# macOS voices. `say -v '?'` lists what is installed on this machine.
DEFAULT_SPEAKERS: tuple[Speaker, ...] = (
    Speaker(
        "en-female",
        "Samantha",
        "The recording was made in a small room with the window open. "
        "You can hear traffic outside, and the air conditioning never stops. "
        "None of that belongs in the final cut.",
    ),
    Speaker(
        "en-male",
        "Fred",
        "I set the microphone too far away and the gain too high. "
        "Half the interview is unusable, and the other half needs work. "
        "Let us see how much of it can be recovered.",
    ),
    Speaker(
        "es-female",
        "Paulina",
        "La entrevista se grabó en una cafetería a media tarde. "
        "Hay conversaciones de fondo, música y el ruido de la máquina de café. "
        "Solo interesa conservar una voz.",
    ),
)


def _normalise(signal: NDArray[np.float64]) -> NDArray[np.float32]:
    peak = float(np.max(np.abs(signal)))
    if peak <= 0.0:
        raise FixtureError("generated a silent signal")
    return (signal / peak * PEAK).astype(np.float32)


def make_noise(
    kind: str,
    samples: int,
    sample_rate: int,
    rng: np.random.Generator,
) -> NDArray[np.float32]:
    """Generate one noise type. Same seed in, same samples out."""
    if kind not in NOISE_KINDS:
        raise FixtureError(f"unknown noise kind: {kind}")

    white = rng.normal(0.0, 1.0, samples)

    if kind == "white":
        return _normalise(white)

    if kind == "brown":
        # Integrating white noise gives a -6 dB/octave slope: the dull, low
        # rumble of traffic and air conditioning rather than tape hiss.
        brown = np.cumsum(white)
        return _normalise(brown - brown.mean())

    t = np.arange(samples) / sample_rate

    if kind == "music":
        return _make_music(t, samples, white)

    # Mains hum: a strong fundamental with decaying harmonics, plus a whisper of
    # broadband noise so it is not a mathematically perfect tone.
    hum = sum(
        amplitude * np.sin(2.0 * math.pi * MAINS_HZ * harmonic * t)
        for harmonic, amplitude in ((1, 1.0), (2, 0.4), (3, 0.2))
    )
    return _normalise(hum + 0.02 * white)


def _make_music(
    t: NDArray[np.float64],
    samples: int,
    white: NDArray[np.float64],
) -> NDArray[np.float32]:
    """A gated chord loop over a bass line and a beat."""
    beat = 60.0 / MUSIC_TEMPO_BPM
    bar = 4.0 * beat

    bar_index = np.floor(t / bar).astype(int)
    into_bar = t - bar_index * bar
    chord_envelope = np.exp(-1.5 * into_bar)

    track = np.zeros(samples)

    for index, chord in enumerate(MUSIC_PROGRESSION):
        active = (bar_index % len(MUSIC_PROGRESSION)) == index
        root_hz = MUSIC_ROOT_HZ * 2.0 ** (chord[0] / 12.0)

        # Bass an octave below the chord root: the band that overlaps a low voice.
        track += active * 0.9 * chord_envelope * np.sin(math.pi * root_hz * t)

        for semitone in chord:
            freq = MUSIC_ROOT_HZ * 2.0 ** (semitone / 12.0)
            for harmonic, amplitude in ((1, 1.0), (2, 0.35), (3, 0.15)):
                track += (
                    active
                    * 0.2
                    * amplitude
                    * chord_envelope
                    * np.sin(2.0 * math.pi * freq * harmonic * t)
                )

    # Percussion: a short broadband burst on every beat.
    into_beat = t - np.floor(t / beat) * beat
    track += 0.15 * np.exp(-45.0 * into_beat) * white

    return _normalise(track)


def _snr_tag(snr_db: float) -> str:
    sign = "m" if snr_db < 0 else ""
    return f"{sign}{abs(round(snr_db)):02d}"


def plan_corpus(
    speakers: tuple[Speaker, ...],
    noise_kinds: tuple[str, ...],
    snr_levels: tuple[float, ...],
) -> tuple[CorpusEntry, ...]:
    """Enumerate every combination the corpus will contain."""
    if not speakers:
        raise FixtureError("plan_corpus needs at least one speaker")
    if not noise_kinds:
        raise FixtureError("plan_corpus needs at least one noise kind")
    if not snr_levels:
        raise FixtureError("plan_corpus needs at least one SNR level")

    return tuple(
        CorpusEntry(
            speaker=speaker.key,
            noise=noise,
            snr_db=snr,
            clean=f"clean/{speaker.key}.wav",
            noisy=f"noisy/{speaker.key}_{noise}_snr{_snr_tag(snr)}.wav",
        )
        for speaker in speakers
        for noise in noise_kinds
        for snr in snr_levels
    )


def _require(binary: str, hint: str) -> str:
    path = shutil.which(binary)
    if path is None:
        raise FixtureError(f"{binary} is not installed or not in PATH. {hint}")
    return path


def synthesize(speaker: Speaker, output_path: Path, sample_rate: int) -> None:
    """Render one speaker's line to mono PCM at the requested rate."""
    say = _require("say", "It ships with macOS; this generator is macOS only.")
    ffmpeg = _require("ffmpeg", "Install it with: brew install ffmpeg")

    with tempfile.TemporaryDirectory() as scratch:
        raw = Path(scratch) / "speech.aiff"

        spoken = subprocess.run(  # noqa: S603 — fixed binary, argument array, no shell
            [say, "-v", speaker.voice, "-o", str(raw), speaker.text],
            capture_output=True,
            text=True,
            check=False,
        )
        if spoken.returncode != 0:
            raise FixtureError(
                f"say failed for voice {speaker.voice!r}: {spoken.stderr.strip()}. "
                "Run `say -v '?'` to see the voices installed on this machine."
            )

        converted = subprocess.run(  # noqa: S603
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(raw),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if converted.returncode != 0:
            raise FixtureError(f"ffmpeg failed converting speech: {converted.stderr.strip()}")


def build_conversations(
    out_dir: Path,
    speech: dict[str, NDArray[np.float32]],
    sample_rate: int,
) -> list[dict[str, Any]]:
    """Render every multi-speaker scenario, with the ground truth F3 needs."""
    (out_dir / "conversations").mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        turns = plan_turns(scenario.order, CONVERSATION_TURN_MS, scenario.overlap)
        mixture, references = render(turns, speech, sample_rate, scenario.gains_db)

        mixture_path = f"conversations/{scenario.key}.wav"
        sf.write(out_dir / mixture_path, mixture, sample_rate)

        reference_paths: dict[str, str] = {}
        for speaker, track in sorted(references.items()):
            path = f"conversations/{scenario.key}_{speaker}.wav"
            sf.write(out_dir / path, track, sample_rate)
            reference_paths[speaker] = path

        records.append(
            {
                "key": scenario.key,
                "mixture": mixture_path,
                "references": reference_paths,
                "dominant": dominant_speaker(turns, scenario.gains_db),
                "intended": scenario.intended,
                "turns": [asdict(turn) for turn in turns],
            }
        )

    return records


def generate(out_dir: Path, seed: int, sample_rate: int) -> tuple[CorpusEntry, ...]:
    """Build the whole corpus under `out_dir`, write the manifest, return the entries."""
    for sub in ("clean", "noise", "noisy"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    speech: dict[str, NDArray[np.float32]] = {}
    for speaker in DEFAULT_SPEAKERS:
        clean_path = out_dir / "clean" / f"{speaker.key}.wav"
        synthesize(speaker, clean_path, sample_rate)
        samples, _ = sf.read(clean_path, dtype="float32", always_2d=False)
        speech[speaker.key] = samples

    longest = max(len(samples) for samples in speech.values())

    noises: dict[str, NDArray[np.float32]] = {}
    for kind in NOISE_KINDS:
        noise = make_noise(kind, longest, sample_rate, np.random.default_rng(seed))
        sf.write(out_dir / "noise" / f"{kind}.wav", noise, sample_rate)
        noises[kind] = noise

    entries = plan_corpus(DEFAULT_SPEAKERS, NOISE_KINDS, DEFAULT_SNR_LEVELS)
    for entry in entries:
        mixture, _ = mix_at_snr(speech[entry.speaker], noises[entry.noise], entry.snr_db)
        sf.write(out_dir / entry.noisy, mixture, sample_rate)

    manifest = {
        "sample_rate": sample_rate,
        "seed": seed,
        "entries": [asdict(entry) for entry in entries],
        "conversations": build_conversations(out_dir, speech, sample_rate),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="kov-fixtures",
        description="Generate the reproducible test corpus used to measure cleaning quality.",
    )
    parser.add_argument("--out", type=Path, default=Path("../fixtures/generated"))
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    args = parser.parse_args()

    try:
        entries = generate(args.out.resolve(), args.seed, args.sample_rate)
    except FixtureError as exc:
        print(f"error: {exc}")
        return 1

    print(
        f"wrote {len(entries)} noise mixtures and {len(SCENARIOS)} conversations "
        f"to {args.out.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

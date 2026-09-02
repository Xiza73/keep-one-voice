"""F4: optional transcription of the resulting track with faster-whisper.

Optional in the real sense: it is not in the default stage list. Whisper is slow
and most people only want the clean audio, so transcription happens when asked
for and not before.

This module returns segments, not a file. Where the transcript lands is the
CLI's decision, the same as the audio output path.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kov_worker.audio import quiet_stdout, resample
from kov_worker.protocol import TranscriptSegment

WHISPER_SAMPLE_RATE = 16_000
DEFAULT_WHISPER_MODEL = "base"

RawSegment = tuple[float, float, str]

_model: tuple[str, Any] | None = None


class TranscribeError(RuntimeError):
    """Raised when transcription cannot run at all."""


def to_transcript(raw: Iterable[RawSegment]) -> tuple[TranscriptSegment, ...]:
    """Turn whisper's (start, end, text) tuples into the wire contract."""
    segments = []

    for start_s, end_s, text in raw:
        cleaned = str(text).strip()
        start_ms = round(start_s * 1_000.0)
        end_ms = round(end_s * 1_000.0)

        if not cleaned or end_ms <= start_ms:
            continue

        segments.append(TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=cleaned))

    return tuple(segments)


def _known_models() -> set[str] | None:
    """The catalogue, when faster-whisper still exposes it.

    Returns None rather than failing if the private list moves: a name check is
    a courtesy, not a reason to block someone from transcribing.
    """
    try:
        from faster_whisper.utils import _MODELS

        return set(_MODELS)
    except Exception:
        return None


def _model_name() -> str:
    name = os.environ.get("KOV_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    known = _known_models()

    if known is not None and name not in known:
        raise TranscribeError(
            f"unknown whisper model {name!r}. Set KOV_WHISPER_MODEL to one of: "
            f"{', '.join(sorted(known))}"
        )

    return name


def _load(name: str) -> Any:
    global _model

    if _model is not None and _model[0] == name:
        return _model[1]

    try:
        with quiet_stdout():
            from faster_whisper import WhisperModel

            # int8 on CPU: a transcript is a convenience, not the deliverable.
            model = WhisperModel(name, device="cpu", compute_type="int8")
    except ImportError as exc:
        raise TranscribeError(
            "faster-whisper is not installed. Set it up with: "
            "cd worker && uv sync --extra transcribe"
        ) from exc
    except Exception as exc:
        raise TranscribeError(
            f"could not load whisper model {name!r} ({type(exc).__name__})"
        ) from None

    _model = (name, model)
    return model


def transcribe_samples(
    samples: NDArray[np.float32],
    sample_rate: int,
) -> tuple[TranscriptSegment, ...]:
    """Transcribe the track. Returns text with timings; the audio is untouched."""
    name = _model_name()
    model = _load(name)

    audio = resample(samples, sample_rate, WHISPER_SAMPLE_RATE)

    try:
        with quiet_stdout():
            # The result is a generator; it has to be consumed while the model
            # call is still in scope.
            found, _info = model.transcribe(audio, beam_size=1)
            raw = [(float(item.start), float(item.end), str(item.text)) for item in found]
    except Exception as exc:
        raise TranscribeError(f"transcription failed ({type(exc).__name__})") from exc

    return to_transcript(raw)

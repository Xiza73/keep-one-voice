"""F3, first half: find out who speaks when, with pyannote 3.1.

This is the only stage behind a manual gate. `pyannote/speaker-diarization-3.1`
requires accepting its licence on the model page and a Hugging Face token in the
environment. There is no way around it, so the failure says so in those words
rather than surfacing a download error.

Diarization runs at 16 kHz. That is fine: it produces timestamps, not audio, so
its rate never touches what the listener hears. Loudness is measured back on the
original audio, at the pipeline's own rate.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kov_worker.audio import quiet_stdout, resample
from kov_worker.protocol import SpeakerSegment

DIARIZE_SAMPLE_RATE = 16_000
PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"
LICENCE_URL = f"https://hf.co/{PYANNOTE_MODEL}"

# Reported instead of -inf so the value stays usable in comparisons and JSON.
SILENCE_DBFS = -120.0

Span = tuple[str, float, float]

_pipeline: Any | None = None


class DiarizeError(RuntimeError):
    """Raised when diarization cannot run. Never carries the token."""


def measure_dbfs(
    samples: NDArray[np.float32],
    sample_rate: int,
    start_ms: int,
    end_ms: int,
) -> float:
    """Mean loudness over a span, in dBFS. Used to break ties between speakers."""
    total = len(samples)
    start = min(max(round(start_ms / 1_000.0 * sample_rate), 0), total)
    end = min(max(round(end_ms / 1_000.0 * sample_rate), 0), total)

    if end <= start:
        return SILENCE_DBFS

    rms = float(np.sqrt(np.mean(np.square(samples[start:end], dtype=np.float64))))
    if rms <= 0.0:
        return SILENCE_DBFS

    return max(20.0 * math.log10(rms), SILENCE_DBFS)


def to_segments(
    spans: Iterable[Span],
    samples: NDArray[np.float32],
    sample_rate: int,
) -> tuple[SpeakerSegment, ...]:
    """Turn pyannote's (speaker, start, end) spans into the wire contract."""
    segments = []

    for speaker, start_s, end_s in spans:
        start_ms = round(start_s * 1_000.0)
        end_ms = round(end_s * 1_000.0)
        if end_ms <= start_ms:
            continue

        segments.append(
            SpeakerSegment(
                speaker_id=str(speaker),
                start_ms=start_ms,
                end_ms=end_ms,
                mean_dbfs=measure_dbfs(samples, sample_rate, start_ms, end_ms),
            )
        )

    return tuple(sorted(segments, key=lambda segment: (segment.start_ms, segment.speaker_id)))


def _token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise DiarizeError(
            f"{PYANNOTE_MODEL} is a gated model. Accept its licence at {LICENCE_URL} "
            "and export a Hugging Face access token as HF_TOKEN before running diarization."
        )
    return token


def _load() -> Any:
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    token = _token()

    try:
        with quiet_stdout():
            from pyannote.audio import Pipeline

            pipeline = Pipeline.from_pretrained(PYANNOTE_MODEL, use_auth_token=token)
    except ImportError as exc:
        raise DiarizeError(
            "pyannote is not installed. Set it up with: cd worker && uv sync --extra diarize"
        ) from exc
    except Exception as exc:
        # Never let the token reach a message: the cause may quote the request.
        raise DiarizeError(
            f"could not load {PYANNOTE_MODEL}. Confirm the licence is accepted at "
            f"{LICENCE_URL} and that HF_TOKEN is valid. ({type(exc).__name__})"
        ) from None

    if pipeline is None:
        raise DiarizeError(
            f"{PYANNOTE_MODEL} returned no pipeline, which means the licence at "
            f"{LICENCE_URL} has not been accepted for this account."
        )

    _pipeline = pipeline
    return pipeline


def diarize_samples(
    samples: NDArray[np.float32],
    sample_rate: int,
) -> tuple[SpeakerSegment, ...]:
    """Report who speaks when. Returns timestamps; the audio is untouched."""
    pipeline = _load()

    import torch

    at_model_rate = resample(samples, sample_rate, DIARIZE_SAMPLE_RATE)
    waveform = torch.from_numpy(at_model_rate).unsqueeze(0)

    try:
        with quiet_stdout(), torch.no_grad():
            annotation = pipeline({"waveform": waveform, "sample_rate": DIARIZE_SAMPLE_RATE})
    except Exception as exc:
        raise DiarizeError(f"diarization failed ({type(exc).__name__})") from None

    spans: list[Span] = [
        (str(speaker), float(turn.start), float(turn.end))
        for turn, _track, speaker in annotation.itertracks(yield_label=True)
    ]

    return to_segments(spans, samples, sample_rate)

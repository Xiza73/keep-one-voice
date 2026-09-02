"""F3, second half: keep only the chosen speaker.

Deliberately model-free. Once diarization has said who talks when, extracting
one voice is a masking problem, so this stage costs nothing to run and needs no
weights, no token and no network.

The honest limitation: where two people talk at once, the mask keeps both. This
is turn masking, not target-speaker separation. The corpus has overlap scenarios
precisely so that limit shows up as a number.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from kov_worker.protocol import SpeakerSegment

# A hard cut at a turn boundary is an audible click, so the mask ramps instead.
FADE_MS = 15.0


class ExtractError(RuntimeError):
    """Raised when the requested speaker cannot be extracted."""


def extract_speaker(
    samples: NDArray[np.float32],
    sample_rate: int,
    segments: tuple[SpeakerSegment, ...],
    speaker: str,
) -> NDArray[np.float32]:
    """Silence everything outside the chosen speaker's turns."""
    if not segments:
        raise ExtractError("no speech was detected, so there is no speaker to extract")

    mine = [segment for segment in segments if segment.speaker_id == speaker]
    if not mine:
        found = sorted({segment.speaker_id for segment in segments})
        raise ExtractError(f"no turns for speaker {speaker!r}; diarization found: {found}")

    total = len(samples)
    mask = np.zeros(total, dtype=np.float64)

    for segment in mine:
        start = min(max(round(segment.start_ms / 1_000.0 * sample_rate), 0), total)
        end = min(max(round(segment.end_ms / 1_000.0 * sample_rate), 0), total)
        if end > start:
            mask[start:end] = 1.0

    ramp = int(FADE_MS / 1_000.0 * sample_rate)
    if ramp > 1:
        window = np.hanning(2 * ramp + 1)
        mask = np.convolve(mask, window / window.sum(), mode="same")

    return (samples * mask).astype(np.float32)

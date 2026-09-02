"""F2: separate the voice from music and instruments with Demucs v4.

Demucs splits a mix into drums, bass, other and vocals; this stage keeps the
vocals stem and discards the rest.

Two conversions are unavoidable. Demucs runs at 44.1 kHz while the pipeline runs
at 48 kHz, and it expects stereo while the pipeline is mono. Both are undone
before returning, so the caller gets back what it gave.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from kov_worker.audio import fit_length, quiet_stdout, resample

DEMUCS_SAMPLE_RATE = 44_100
DEMUCS_MODEL = "htdemucs"
VOCALS_STEM = "vocals"

_model: Any | None = None


class SeparateError(RuntimeError):
    """Raised when the separator cannot run at all."""


def _load() -> Any:
    global _model

    if _model is not None:
        return _model

    try:
        with quiet_stdout():
            from demucs.pretrained import get_model

            model = get_model(DEMUCS_MODEL)
    except ImportError as exc:
        raise SeparateError(
            "Demucs is not installed. Set it up with: cd worker && uv sync --extra separate"
        ) from exc

    if VOCALS_STEM not in model.sources:
        raise SeparateError(
            f"{DEMUCS_MODEL} produces {model.sources}, which has no {VOCALS_STEM!r} stem"
        )
    if model.samplerate != DEMUCS_SAMPLE_RATE:
        raise SeparateError(
            f"{DEMUCS_MODEL} reports {model.samplerate} Hz "
            f"but this module assumes {DEMUCS_SAMPLE_RATE} Hz"
        )

    model.eval()
    _model = model
    return model


def separate_samples(samples: NDArray[np.float32], sample_rate: int) -> NDArray[np.float32]:
    """Keep the vocals stem, at the rate the caller provided."""
    import torch
    from demucs.apply import apply_model

    model = _load()

    original_length = len(samples)
    at_model_rate = resample(samples, sample_rate, DEMUCS_SAMPLE_RATE)

    # (batch, channels, length): mono duplicated into both channels.
    mono = torch.from_numpy(at_model_rate)
    stereo = mono.unsqueeze(0).repeat(model.audio_channels, 1).unsqueeze(0)

    with quiet_stdout(), torch.no_grad():
        stems = apply_model(model, stereo, device="cpu", progress=False)[0]

    vocals = stems[model.sources.index(VOCALS_STEM)].mean(dim=0)
    back = resample(vocals.numpy().astype(np.float32), DEMUCS_SAMPLE_RATE, sample_rate)

    return fit_length(back, original_length)

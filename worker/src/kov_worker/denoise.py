"""F1: background noise removal with DeepFilterNet 3.

The model is loaded once per process and cached: initialisation costs about a
second, and the worker may be asked for several stages in one run.

DeepFilterNet 3 runs at 48 kHz. Audio arriving at another rate is resampled in
and back out, so the caller gets what it gave.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from kov_worker.audio import fit_length, quiet_stdout, resample

DF_SAMPLE_RATE = 48_000

_model: tuple[Any, Any] | None = None


class DenoiseError(RuntimeError):
    """Raised when the denoiser cannot run at all."""


def _load() -> tuple[Any, Any]:
    global _model

    if _model is not None:
        return _model

    try:
        with quiet_stdout():
            from df.enhance import init_df

            model, state, _suffix = init_df(log_level="ERROR")
    except ImportError as exc:
        raise DenoiseError(
            "DeepFilterNet is not installed. Set it up with: cd worker && uv sync --extra denoise"
        ) from exc

    if state.sr() != DF_SAMPLE_RATE:
        raise DenoiseError(
            f"DeepFilterNet reports {state.sr()} Hz but this module assumes {DF_SAMPLE_RATE} Hz"
        )

    _model = (model, state)
    return _model


def denoise_samples(samples: NDArray[np.float32], sample_rate: int) -> NDArray[np.float32]:
    """Remove background noise, returning audio at the rate it was given."""
    import torch
    from df.enhance import enhance

    model, state = _load()

    original_length = len(samples)
    at_model_rate = resample(samples, sample_rate, DF_SAMPLE_RATE)

    with quiet_stdout(), torch.no_grad():
        enhanced = enhance(model, state, torch.from_numpy(at_model_rate).unsqueeze(0))

    cleaned = resample(enhanced.squeeze(0).numpy().astype(np.float32), DF_SAMPLE_RATE, sample_rate)

    return fit_length(cleaned, original_length)

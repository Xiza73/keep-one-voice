"""F1: background noise removal with DeepFilterNet3.

The model is loaded once per process and cached: initialisation costs about a
second, and the worker may be asked for several stages in one run.

Two things this module is careful about:

- **stdout is the protocol channel.** DeepFilterNet and torch log freely, and a
  stray line on stdout corrupts the response the CLI is parsing. Everything the
  model prints is redirected to stderr.
- **DeepFilterNet3 runs at 48 kHz.** Audio arriving at another rate is resampled
  in and back out, so the caller gets what it gave.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from typing import Any

import numpy as np
from numpy.typing import NDArray

DF_SAMPLE_RATE = 48_000

_model: tuple[Any, Any] | None = None


class DenoiseError(RuntimeError):
    """Raised when the denoiser cannot run at all."""


@contextlib.contextmanager
def _quiet_stdout() -> Iterator[None]:
    """Keep third-party chatter off the protocol channel."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _load() -> tuple[Any, Any]:
    global _model

    if _model is not None:
        return _model

    try:
        with _quiet_stdout():
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


def _resample(samples: NDArray[np.float32], source: int, target: int) -> NDArray[np.float32]:
    if source == target:
        return samples

    import torch
    import torchaudio.functional as ta

    resampled = ta.resample(torch.from_numpy(samples), source, target)
    return resampled.numpy().astype(np.float32)


def denoise_samples(samples: NDArray[np.float32], sample_rate: int) -> NDArray[np.float32]:
    """Remove background noise, returning audio at the rate it was given."""
    import torch
    from df.enhance import enhance

    model, state = _load()

    original_length = len(samples)
    at_model_rate = _resample(samples, sample_rate, DF_SAMPLE_RATE)

    with _quiet_stdout():
        enhanced = enhance(model, state, torch.from_numpy(at_model_rate).unsqueeze(0))

    cleaned = _resample(enhanced.squeeze(0).numpy().astype(np.float32), DF_SAMPLE_RATE, sample_rate)

    # Resampling can round the sample count up or down by a frame or two.
    if len(cleaned) > original_length:
        return cleaned[:original_length]
    if len(cleaned) < original_length:
        return np.pad(cleaned, (0, original_length - len(cleaned)))
    return cleaned

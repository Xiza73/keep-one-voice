"""Helpers every model stage needs.

Each model has its own native sample rate — DeepFilterNet 3 at 48 kHz, Demucs at
44.1 kHz — so resampling in and back out belongs to the stage, not to the
pipeline. A stage always returns audio at the rate it was handed.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator

import numpy as np
from numpy.typing import NDArray


@contextlib.contextmanager
def quiet_stdout() -> Iterator[None]:
    """Keep third-party chatter off the protocol channel.

    The worker answers the CLI on stdout. Model stacks log freely, and a single
    stray line corrupts the response being parsed on the other side.
    """
    with contextlib.redirect_stdout(sys.stderr):
        yield


def resample(samples: NDArray[np.float32], source: int, target: int) -> NDArray[np.float32]:
    if source == target:
        return samples

    import torch
    import torchaudio.functional as ta

    return ta.resample(torch.from_numpy(samples), source, target).numpy().astype(np.float32)


def fit_length(samples: NDArray[np.float32], length: int) -> NDArray[np.float32]:
    """Force the sample count back to what the caller gave us.

    Resampling rounds the count up or down by a frame or two. Callers compare
    the result against a reference of a known length, so the drift has to go.
    """
    if len(samples) > length:
        return samples[:length]
    if len(samples) < length:
        return np.pad(samples, (0, length - len(samples)))
    return samples

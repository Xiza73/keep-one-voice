"""Objective audio quality measurement.

"Sounds better" is not a criterion anyone can verify. Every claim about a
cleaning stage in this project has to come from a number produced here, computed
against a known-clean reference signal.

Everything is computed in float64 regardless of the input dtype: SI-SDR is a
ratio of energies, and float32 accumulation over a long signal loses precision
exactly where it matters.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

Signal = NDArray[np.floating]


class MetricError(ValueError):
    """Raised when a measurement is not defined for the given signals."""


def _as_float64(signal: Signal) -> NDArray[np.float64]:
    array = np.asarray(signal, dtype=np.float64)
    if array.ndim != 1:
        raise MetricError("signals must be mono (one dimensional)")
    return array


def _energy(signal: NDArray[np.float64]) -> float:
    return float(np.dot(signal, signal))


def si_sdr(reference: Signal, estimate: Signal) -> float:
    """Scale-invariant signal-to-distortion ratio, in decibels.

    Scale invariance is the point: a denoiser that gets the waveform right but
    the gain wrong should not be punished for it. Returns +inf for a perfect
    estimate.
    """
    ref = _as_float64(reference)
    est = _as_float64(estimate)

    if ref.shape != est.shape:
        raise MetricError("reference and estimate must have the same length")

    reference_energy = _energy(ref)
    if reference_energy <= 0.0:
        raise MetricError("reference is silent, so there is no signal to recover")

    alpha = float(np.dot(est, ref)) / reference_energy
    target = alpha * ref
    error = est - target

    error_energy = _energy(error)
    if error_energy <= 0.0:
        return math.inf

    target_energy = _energy(target)
    if target_energy <= 0.0:
        return -math.inf

    return 10.0 * math.log10(target_energy / error_energy)


def snr_db(signal: Signal, noise: Signal) -> float:
    """Plain signal-to-noise ratio in decibels, when both parts are known."""
    sig = _as_float64(signal)
    noi = _as_float64(noise)

    if sig.shape != noi.shape:
        raise MetricError("signal and noise must have the same length")

    noise_energy = _energy(noi)
    if noise_energy <= 0.0:
        raise MetricError("noise is silent, so the ratio is undefined")

    signal_energy = _energy(sig)
    if signal_energy <= 0.0:
        return -math.inf

    return 10.0 * math.log10(signal_energy / noise_energy)


def _fit_length(signal: NDArray[np.float64], length: int) -> NDArray[np.float64]:
    if len(signal) >= length:
        return signal[:length]
    repeats = math.ceil(length / len(signal))
    return np.tile(signal, repeats)[:length]


def mix_at_snr(
    speech: Signal,
    noise: Signal,
    target_snr_db: float,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Mix noise into speech at an exact SNR.

    Returns the mixture and the noise component that went into it. Keeping the
    noise is what makes the corpus measurable later: the caller can recover the
    clean part as `mixture - noise` and verify the SNR it asked for.

    The mixture is scaled down if it would clip. Both returned signals get the
    same scaling, so the SNR is preserved and SI-SDR — being scale invariant —
    is unaffected.
    """
    clean = _as_float64(speech)
    raw_noise = _as_float64(noise)

    if _energy(clean) <= 0.0:
        raise MetricError("speech is silent, so there is nothing to mix into")
    if _energy(raw_noise) <= 0.0:
        raise MetricError("noise is silent, so it cannot be scaled to an SNR")

    fitted = _fit_length(raw_noise, len(clean))

    ratio = 10.0 ** (target_snr_db / 10.0)
    scale = math.sqrt(_energy(clean) / (_energy(fitted) * ratio))
    scaled_noise = fitted * scale

    mixture = clean + scaled_noise

    peak = float(np.max(np.abs(mixture)))
    if peak > 1.0:
        headroom = 0.99 / peak
        mixture *= headroom
        scaled_noise *= headroom

    return mixture.astype(np.float32), scaled_noise.astype(np.float32)

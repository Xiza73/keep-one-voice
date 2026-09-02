import math

import numpy as np
import pytest

from kov_worker.metrics import MetricError, mix_at_snr, si_sdr, snr_db

RNG = np.random.default_rng(1234)


def noise_like(reference: np.ndarray) -> np.ndarray:
    return RNG.normal(0.0, 1.0, size=reference.shape).astype(np.float32)


class TestSiSdr:
    def test_a_perfect_estimate_is_infinite(self):
        reference = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32)

        assert si_sdr(reference, reference.copy()) == math.inf

    def test_an_orthogonal_error_of_equal_energy_is_zero_decibels(self):
        reference = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32)
        error = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)

        assert si_sdr(reference, reference + error) == pytest.approx(0.0, abs=1e-6)

    def test_is_invariant_to_the_scale_of_the_estimate(self):
        reference = RNG.normal(0.0, 1.0, 4_000).astype(np.float32)
        estimate = reference + 0.1 * noise_like(reference)

        assert si_sdr(reference, estimate) == pytest.approx(si_sdr(reference, 7.5 * estimate))

    def test_more_noise_scores_worse(self):
        reference = RNG.normal(0.0, 1.0, 4_000).astype(np.float32)
        noise = noise_like(reference)

        gentle = si_sdr(reference, reference + 0.05 * noise)
        harsh = si_sdr(reference, reference + 0.5 * noise)

        assert gentle > harsh

    def test_rejects_a_length_mismatch_instead_of_broadcasting(self):
        with pytest.raises(MetricError, match="same length"):
            si_sdr(np.zeros(10, dtype=np.float32), np.zeros(11, dtype=np.float32))

    def test_rejects_a_silent_reference(self):
        with pytest.raises(MetricError, match="silent"):
            si_sdr(np.zeros(10, dtype=np.float32), np.ones(10, dtype=np.float32))


class TestSnrDb:
    def test_equal_energy_is_zero_decibels(self):
        signal = np.array([1.0, -1.0], dtype=np.float32)
        noise = np.array([1.0, 1.0], dtype=np.float32)

        assert snr_db(signal, noise) == pytest.approx(0.0, abs=1e-6)

    def test_ten_times_the_power_is_ten_decibels(self):
        signal = np.full(100, math.sqrt(10.0), dtype=np.float32)
        noise = np.ones(100, dtype=np.float32)

        assert snr_db(signal, noise) == pytest.approx(10.0, abs=1e-4)

    def test_rejects_silent_noise(self):
        with pytest.raises(MetricError, match="silent"):
            snr_db(np.ones(10, dtype=np.float32), np.zeros(10, dtype=np.float32))


class TestMixAtSnr:
    @pytest.mark.parametrize("target", [0.0, 5.0, 10.0, 20.0])
    def test_the_mix_lands_on_the_requested_snr(self, target):
        speech = RNG.normal(0.0, 0.2, 16_000).astype(np.float32)
        noise = RNG.normal(0.0, 1.0, 16_000).astype(np.float32)

        mixed, scaled_noise = mix_at_snr(speech, noise, target)

        assert snr_db(mixed - scaled_noise, scaled_noise) == pytest.approx(target, abs=1e-3)

    def test_keeps_the_length_of_the_speech(self):
        speech = RNG.normal(0.0, 0.2, 16_000).astype(np.float32)
        noise = RNG.normal(0.0, 1.0, 16_000).astype(np.float32)

        mixed, _ = mix_at_snr(speech, noise, 10.0)

        assert len(mixed) == len(speech)

    def test_tiles_noise_that_is_shorter_than_the_speech(self):
        speech = RNG.normal(0.0, 0.2, 16_000).astype(np.float32)
        noise = RNG.normal(0.0, 1.0, 4_000).astype(np.float32)

        mixed, _ = mix_at_snr(speech, noise, 10.0)

        assert len(mixed) == 16_000

    def test_trims_noise_that_is_longer_than_the_speech(self):
        speech = RNG.normal(0.0, 0.2, 4_000).astype(np.float32)
        noise = RNG.normal(0.0, 1.0, 16_000).astype(np.float32)

        mixed, _ = mix_at_snr(speech, noise, 10.0)

        assert len(mixed) == 4_000

    def test_never_clips(self):
        speech = np.full(1_000, 0.9, dtype=np.float32)
        noise = np.full(1_000, 0.9, dtype=np.float32)

        mixed, _ = mix_at_snr(speech, noise, 0.0)

        assert np.max(np.abs(mixed)) <= 1.0

    def test_scaling_down_to_avoid_clipping_preserves_the_snr(self):
        speech = np.full(1_000, 0.9, dtype=np.float32)
        noise = RNG.normal(0.0, 1.0, 1_000).astype(np.float32)

        mixed, scaled_noise = mix_at_snr(speech, noise, 6.0)

        assert snr_db(mixed - scaled_noise, scaled_noise) == pytest.approx(6.0, abs=1e-3)

    def test_rejects_silent_speech(self):
        with pytest.raises(MetricError, match="silent"):
            mix_at_snr(np.zeros(100, dtype=np.float32), np.ones(100, dtype=np.float32), 10.0)

    def test_rejects_silent_noise(self):
        with pytest.raises(MetricError, match="silent"):
            mix_at_snr(np.ones(100, dtype=np.float32), np.zeros(100, dtype=np.float32), 10.0)

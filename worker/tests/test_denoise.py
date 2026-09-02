"""Quality tests for the denoise stage.

These are slow: they load DeepFilterNet3 and synthesise speech. They are also
the only tests that say anything about whether F1 actually works, so they are
not optional. Skipped when the `denoise` extra is not installed.
"""

import shutil

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("df", reason="install the denoise extra: uv sync --extra denoise")

from kov_worker.denoise import DF_SAMPLE_RATE, denoise_samples
from kov_worker.fixtures import Speaker, synthesize
from kov_worker.metrics import mix_at_snr, si_sdr

pytestmark = pytest.mark.slow

SPEAKER = Speaker(
    "test",
    "Samantha",
    "The window was open and the street outside was busy all afternoon.",
)


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    if shutil.which("say") is None:
        pytest.skip("`say` is only available on macOS")

    path = tmp_path_factory.mktemp("speech") / "clean.wav"
    synthesize(SPEAKER, path, DF_SAMPLE_RATE)
    samples, _ = sf.read(path, dtype="float32", always_2d=False)
    return samples


def noisy_at(speech: np.ndarray, snr_db: float) -> np.ndarray:
    noise = np.random.default_rng(4).normal(0.0, 1.0, len(speech)).astype(np.float32)
    mixture, _ = mix_at_snr(speech, noise, snr_db)
    return mixture


class TestDenoiseSamples:
    def test_runs_natively_at_48_kilohertz(self):
        assert DF_SAMPLE_RATE == 48_000

    def test_keeps_the_length_of_the_input(self, speech):
        cleaned = denoise_samples(noisy_at(speech, 5.0), DF_SAMPLE_RATE)

        assert len(cleaned) == len(speech)

    def test_returns_float32_mono(self, speech):
        cleaned = denoise_samples(noisy_at(speech, 5.0), DF_SAMPLE_RATE)

        assert cleaned.dtype == np.float32
        assert cleaned.ndim == 1

    def test_improves_si_sdr_on_noisy_speech(self, speech):
        noisy = noisy_at(speech, 5.0)

        before = si_sdr(speech, noisy)
        after = si_sdr(speech, denoise_samples(noisy, DF_SAMPLE_RATE))

        assert after > before

    def test_helps_most_where_the_noise_is_worst(self, speech):
        quiet_noise = noisy_at(speech, 20.0)
        loud_noise = noisy_at(speech, 0.0)

        gain_at_20 = si_sdr(speech, denoise_samples(quiet_noise, DF_SAMPLE_RATE)) - si_sdr(
            speech, quiet_noise
        )
        gain_at_0 = si_sdr(speech, denoise_samples(loud_noise, DF_SAMPLE_RATE)) - si_sdr(
            speech, loud_noise
        )

        assert gain_at_0 > gain_at_20

    def test_resamples_a_sixteen_kilohertz_input_and_returns_it_at_that_rate(self, speech):
        import torch
        import torchaudio.functional as ta

        downsampled = (
            ta.resample(torch.from_numpy(speech), DF_SAMPLE_RATE, 16_000).numpy().astype(np.float32)
        )
        noisy = noisy_at(downsampled, 5.0)

        cleaned = denoise_samples(noisy, 16_000)

        assert len(cleaned) == len(noisy)
        assert si_sdr(downsampled, cleaned) > si_sdr(downsampled, noisy)

    def test_leaves_clean_speech_roughly_intact(self, speech):
        cleaned = denoise_samples(speech, DF_SAMPLE_RATE)

        # Denoising something already clean should not wreck it.
        assert si_sdr(speech, cleaned) > 5.0

"""Quality tests for the separate stage.

Slow: they load Demucs and synthesise both speech and a backing track. They are
also the only evidence that F2 does anything, so they are not optional. Skipped
when the `separate` extra is not installed.
"""

import shutil

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("demucs", reason="install the separate extra: uv sync --extra separate")

from kov_worker.fixtures import Speaker, make_noise, synthesize
from kov_worker.metrics import mix_at_snr, si_sdr
from kov_worker.separate import DEMUCS_SAMPLE_RATE, VOCALS_STEM, separate_samples

pytestmark = pytest.mark.slow

PIPELINE_RATE = 48_000

SPEAKER = Speaker(
    "test",
    "Samantha",
    "There was a band playing in the corner while we tried to talk.",
)


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    if shutil.which("say") is None:
        pytest.skip("`say` is only available on macOS")

    path = tmp_path_factory.mktemp("speech") / "clean.wav"
    synthesize(SPEAKER, path, PIPELINE_RATE)
    samples, _ = sf.read(path, dtype="float32", always_2d=False)
    return samples


@pytest.fixture(scope="module")
def over_music(speech):
    music = make_noise("music", len(speech), PIPELINE_RATE, np.random.default_rng(8))
    mixture, _ = mix_at_snr(speech, music, 0.0)
    return mixture


class TestSeparateSamples:
    def test_runs_natively_at_44100(self):
        assert DEMUCS_SAMPLE_RATE == 44_100

    def test_keeps_the_vocals_stem(self):
        assert VOCALS_STEM == "vocals"

    def test_keeps_the_length_of_the_input(self, speech, over_music):
        assert len(separate_samples(over_music, PIPELINE_RATE)) == len(speech)

    def test_returns_float32_mono(self, over_music):
        stem = separate_samples(over_music, PIPELINE_RATE)

        assert stem.dtype == np.float32
        assert stem.ndim == 1

    def test_improves_si_sdr_on_speech_buried_in_music(self, speech, over_music):
        before = si_sdr(speech, over_music)
        after = si_sdr(speech, separate_samples(over_music, PIPELINE_RATE))

        assert after > before

    def test_removes_more_music_than_it_removes_voice(self, speech):
        music = make_noise("music", len(speech), PIPELINE_RATE, np.random.default_rng(8))
        mixture, scaled_music = mix_at_snr(speech, music, 0.0)

        stem = separate_samples(mixture, PIPELINE_RATE)

        # The stem should look far more like the speech than like the music.
        assert si_sdr(speech, stem) > si_sdr(scaled_music, stem)

    def test_leaves_speech_without_music_roughly_intact(self, speech):
        stem = separate_samples(speech, PIPELINE_RATE)

        assert si_sdr(speech, stem) > 5.0

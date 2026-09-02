import numpy as np
import pytest

from kov_worker.fixtures import (
    NOISE_KINDS,
    FixtureError,
    Speaker,
    make_noise,
    plan_corpus,
)

SAMPLE_RATE = 16_000


def spectral_centroid(signal: np.ndarray, sample_rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    return float((freqs * spectrum).sum() / spectrum.sum())


def dominant_frequency(signal: np.ndarray, sample_rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
    return float(freqs[int(np.argmax(spectrum))])


class TestMakeNoise:
    @pytest.mark.parametrize("kind", NOISE_KINDS)
    def test_returns_the_requested_number_of_samples(self, kind):
        noise = make_noise(kind, 8_000, SAMPLE_RATE, np.random.default_rng(0))

        assert len(noise) == 8_000

    @pytest.mark.parametrize("kind", NOISE_KINDS)
    def test_is_reproducible_for_the_same_seed(self, kind):
        first = make_noise(kind, 4_000, SAMPLE_RATE, np.random.default_rng(7))
        second = make_noise(kind, 4_000, SAMPLE_RATE, np.random.default_rng(7))

        assert np.array_equal(first, second)

    @pytest.mark.parametrize("kind", NOISE_KINDS)
    def test_never_exceeds_full_scale(self, kind):
        noise = make_noise(kind, 8_000, SAMPLE_RATE, np.random.default_rng(3))

        assert np.max(np.abs(noise)) <= 1.0

    @pytest.mark.parametrize("kind", NOISE_KINDS)
    def test_is_not_silent(self, kind):
        noise = make_noise(kind, 8_000, SAMPLE_RATE, np.random.default_rng(3))

        assert float(np.dot(noise, noise)) > 0.0

    def test_white_noise_differs_between_seeds(self):
        first = make_noise("white", 4_000, SAMPLE_RATE, np.random.default_rng(1))
        second = make_noise("white", 4_000, SAMPLE_RATE, np.random.default_rng(2))

        assert not np.array_equal(first, second)

    def test_brown_noise_is_darker_than_white_noise(self):
        rng = np.random.default_rng(11)
        white = make_noise("white", 16_000, SAMPLE_RATE, rng)
        brown = make_noise("brown", 16_000, SAMPLE_RATE, np.random.default_rng(11))

        assert spectral_centroid(brown, SAMPLE_RATE) < spectral_centroid(white, SAMPLE_RATE)

    def test_hum_peaks_at_mains_frequency(self):
        hum = make_noise("hum", 16_000, SAMPLE_RATE, np.random.default_rng(5))

        assert dominant_frequency(hum, SAMPLE_RATE) == pytest.approx(50.0, abs=2.0)

    def test_rejects_an_unknown_kind(self):
        with pytest.raises(FixtureError, match="unknown noise kind"):
            make_noise("thunderstorm", 100, SAMPLE_RATE, np.random.default_rng(0))


class TestPlanCorpus:
    speakers = (
        Speaker("en-female", "Samantha", "One."),
        Speaker("es-female", "Paulina", "Dos."),
    )

    def test_covers_every_combination(self):
        entries = plan_corpus(self.speakers, ("white", "hum"), (0.0, 10.0))

        assert len(entries) == 2 * 2 * 2

    def test_points_each_noisy_file_at_its_clean_reference(self):
        entries = plan_corpus(self.speakers, ("white",), (10.0,))

        assert entries[0].clean == "clean/en-female.wav"
        assert entries[0].noisy == "noisy/en-female_white_snr10.wav"

    def test_encodes_negative_and_padded_snr_in_the_file_name(self):
        entries = plan_corpus(self.speakers[:1], ("white",), (0.0, 5.0, 20.0))

        names = [entry.noisy for entry in entries]
        assert names == [
            "noisy/en-female_white_snr00.wav",
            "noisy/en-female_white_snr05.wav",
            "noisy/en-female_white_snr20.wav",
        ]

    def test_produces_no_duplicate_targets(self):
        entries = plan_corpus(self.speakers, NOISE_KINDS, (0.0, 5.0, 10.0, 20.0))

        assert len({entry.noisy for entry in entries}) == len(entries)

    def test_carries_the_parameters_of_each_entry(self):
        entry = plan_corpus(self.speakers[:1], ("brown",), (5.0,))[0]

        assert entry.speaker == "en-female"
        assert entry.noise == "brown"
        assert entry.snr_db == 5.0

    def test_rejects_an_empty_speaker_list(self):
        with pytest.raises(FixtureError, match="at least one speaker"):
            plan_corpus((), ("white",), (10.0,))

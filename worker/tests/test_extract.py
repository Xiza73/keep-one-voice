import numpy as np
import pytest

from kov_worker.extract import ExtractError, extract_speaker
from kov_worker.protocol import SpeakerSegment

SAMPLE_RATE = 48_000


def tone(seconds: float = 3.0) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(seconds * SAMPLE_RATE), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)


def segment(speaker: str, start_ms: int, end_ms: int) -> SpeakerSegment:
    return SpeakerSegment(speaker, start_ms, end_ms, -20.0)


def at(samples: np.ndarray, seconds: float, window_ms: float = 20.0) -> float:
    """Loudness around a moment.

    A single sample is useless here: a 300 Hz tone crosses zero on every whole
    number of cycles, so point comparisons would pass by accident.
    """
    centre = int(seconds * SAMPLE_RATE)
    half = int(window_ms / 2_000.0 * SAMPLE_RATE)
    chunk = samples[max(0, centre - half) : centre + half]
    return float(np.sqrt(np.mean(chunk**2))) if len(chunk) else 0.0


class TestExtractSpeaker:
    def test_keeps_the_length_of_the_input(self):
        audio = tone()

        kept = extract_speaker(audio, SAMPLE_RATE, (segment("a", 0, 1_000),), "a")

        assert len(kept) == len(audio)

    def test_keeps_audio_inside_the_speakers_turn(self):
        audio = tone()

        kept = extract_speaker(audio, SAMPLE_RATE, (segment("a", 0, 1_000),), "a")

        assert at(kept, 0.5) == pytest.approx(at(audio, 0.5), rel=0.05)

    def test_silences_audio_outside_the_speakers_turn(self):
        audio = tone()

        kept = extract_speaker(audio, SAMPLE_RATE, (segment("a", 0, 1_000),), "a")

        assert at(kept, 2.0) == pytest.approx(0.0, abs=1e-4)

    def test_ignores_turns_that_belong_to_someone_else(self):
        audio = tone()
        segments = (segment("a", 0, 1_000), segment("b", 1_500, 2_500))

        kept = extract_speaker(audio, SAMPLE_RATE, segments, "a")

        assert at(kept, 2.0) == pytest.approx(0.0, abs=1e-4)

    def test_keeps_every_turn_of_the_chosen_speaker(self):
        audio = tone()
        segments = (segment("a", 0, 500), segment("b", 500, 1_500), segment("a", 1_500, 2_500))

        kept = extract_speaker(audio, SAMPLE_RATE, segments, "a")

        assert at(kept, 0.25) > 0.1
        assert at(kept, 2.0) > 0.1
        assert at(kept, 1.0) == pytest.approx(0.0, abs=1e-4)

    def test_does_not_step_abruptly_at_a_turn_boundary(self):
        """A hard cut is an audible click, so the mask has to ramp."""
        audio = tone()

        kept = extract_speaker(audio, SAMPLE_RATE, (segment("a", 0, 1_000),), "a")

        just_after = at(kept, 1.002)
        well_after = at(kept, 1.100)
        assert just_after > well_after

    def test_merges_overlapping_turns_of_the_same_speaker(self):
        audio = tone()
        segments = (segment("a", 0, 1_500), segment("a", 1_000, 2_000))

        kept = extract_speaker(audio, SAMPLE_RATE, segments, "a")

        assert at(kept, 1.2) == pytest.approx(at(audio, 1.2), rel=0.05)

    def test_clamps_a_turn_that_runs_past_the_audio(self):
        audio = tone(1.0)

        kept = extract_speaker(audio, SAMPLE_RATE, (segment("a", 0, 5_000),), "a")

        assert len(kept) == len(audio)

    def test_ignores_a_turn_that_falls_entirely_outside_the_audio(self):
        audio = tone(1.0)
        segments = (segment("a", 0, 500), segment("a", 9_000, 9_500))

        kept = extract_speaker(audio, SAMPLE_RATE, segments, "a")

        assert at(kept, 0.25) > 0.1

    def test_rejects_a_speaker_with_no_turns(self):
        with pytest.raises(ExtractError, match="ghost"):
            extract_speaker(tone(), SAMPLE_RATE, (segment("a", 0, 1_000),), "ghost")

    def test_rejects_an_empty_segment_list(self):
        with pytest.raises(ExtractError, match="no speech"):
            extract_speaker(tone(), SAMPLE_RATE, (), "a")

    def test_returns_float32_mono(self):
        kept = extract_speaker(tone(), SAMPLE_RATE, (segment("a", 0, 1_000),), "a")

        assert kept.dtype == np.float32
        assert kept.ndim == 1

import math

import numpy as np
import pytest

from kov_worker import diarize
from kov_worker.diarize import (
    DIARIZE_SAMPLE_RATE,
    PYANNOTE_MODEL,
    SILENCE_DBFS,
    DiarizeError,
    diarize_samples,
    measure_dbfs,
    to_segments,
)

SAMPLE_RATE = 48_000


def sine(seconds: float, amplitude: float = 1.0) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(seconds * SAMPLE_RATE), endpoint=False)
    return (amplitude * np.sin(2 * math.pi * 300.0 * t)).astype(np.float32)


class TestMeasureDbfs:
    def test_a_full_scale_sine_is_about_minus_three_dbfs(self):
        assert measure_dbfs(sine(1.0), SAMPLE_RATE, 0, 1_000) == pytest.approx(-3.0, abs=0.2)

    def test_a_quieter_span_measures_lower(self):
        loud = np.concatenate([sine(0.5, 1.0), sine(0.5, 0.1)])

        first = measure_dbfs(loud, SAMPLE_RATE, 0, 500)
        second = measure_dbfs(loud, SAMPLE_RATE, 500, 1_000)

        assert first > second

    def test_silence_reports_the_floor(self):
        assert measure_dbfs(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE, 0, 1_000) == (
            SILENCE_DBFS
        )

    def test_clamps_a_span_that_runs_past_the_audio(self):
        assert measure_dbfs(sine(1.0), SAMPLE_RATE, 0, 9_000) > SILENCE_DBFS

    def test_a_span_entirely_outside_the_audio_is_the_floor(self):
        assert measure_dbfs(sine(1.0), SAMPLE_RATE, 5_000, 6_000) == SILENCE_DBFS


class TestToSegments:
    def test_converts_seconds_into_milliseconds(self):
        segments = to_segments((("SPEAKER_00", 0.0, 1.5),), sine(2.0), SAMPLE_RATE)

        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 1_500

    def test_keeps_the_speaker_label(self):
        segments = to_segments((("SPEAKER_01", 0.0, 1.0),), sine(2.0), SAMPLE_RATE)

        assert segments[0].speaker_id == "SPEAKER_01"

    def test_measures_the_loudness_of_each_span(self):
        audio = np.concatenate([sine(0.5, 1.0), sine(0.5, 0.05)])
        spans = (("SPEAKER_00", 0.0, 0.5), ("SPEAKER_01", 0.5, 1.0))

        segments = to_segments(spans, audio, SAMPLE_RATE)

        assert segments[0].mean_dbfs > segments[1].mean_dbfs

    def test_drops_spans_with_no_duration(self):
        spans = (("SPEAKER_00", 1.0, 1.0), ("SPEAKER_00", 1.0, 2.0))

        assert len(to_segments(spans, sine(3.0), SAMPLE_RATE)) == 1

    def test_returns_spans_in_time_order(self):
        spans = (("b", 2.0, 3.0), ("a", 0.0, 1.0))

        segments = to_segments(spans, sine(4.0), SAMPLE_RATE)

        assert [segment.speaker_id for segment in segments] == ["a", "b"]

    def test_an_empty_annotation_yields_no_segments(self):
        assert to_segments((), sine(1.0), SAMPLE_RATE) == ()


class TestGating:
    def test_runs_at_sixteen_kilohertz(self):
        assert DIARIZE_SAMPLE_RATE == 16_000

    def test_names_the_gated_model(self):
        assert PYANNOTE_MODEL == "pyannote/speaker-diarization-3.1"

    def test_without_a_token_it_says_exactly_what_to_do(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)

        with pytest.raises(DiarizeError) as failure:
            diarize_samples(sine(1.0), SAMPLE_RATE)

        message = str(failure.value)
        assert "HF_TOKEN" in message
        assert PYANNOTE_MODEL in message
        assert "licence" in message or "license" in message

    def test_the_token_is_never_echoed_back(self, monkeypatch):
        """Hugging Face errors quote the failing request, token included."""
        secret = "hf_supersecrettokenvalue"  # noqa: S105 — a decoy, not a credential
        monkeypatch.setenv("HF_TOKEN", secret)
        monkeypatch.setattr(diarize, "_pipeline", None)

        from pyannote.audio import Pipeline

        def explode(*_args, **_kwargs):
            raise RuntimeError(f"401 Unauthorized: invalid credential {secret}")

        monkeypatch.setattr(Pipeline, "from_pretrained", explode)

        with pytest.raises(DiarizeError) as failure:
            diarize_samples(sine(0.2), SAMPLE_RATE)

        assert secret not in str(failure.value)
        assert secret not in repr(failure.value.__cause__)
        assert PYANNOTE_MODEL in str(failure.value)

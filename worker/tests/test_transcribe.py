import shutil

import numpy as np
import pytest
import soundfile as sf

from kov_worker.transcribe import (
    DEFAULT_WHISPER_MODEL,
    WHISPER_SAMPLE_RATE,
    TranscribeError,
    to_transcript,
)


class TestToTranscript:
    def test_converts_seconds_into_milliseconds(self):
        segments = to_transcript(((0.0, 1.25, "hello"),))

        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 1_250

    def test_keeps_the_text(self):
        segments = to_transcript(((0.0, 1.0, "the window was open"),))

        assert segments[0].text == "the window was open"

    def test_trims_the_padding_whisper_adds(self):
        segments = to_transcript(((0.0, 1.0, "  hello there  "),))

        assert segments[0].text == "hello there"

    def test_drops_segments_with_no_text(self):
        raw = ((0.0, 1.0, "  "), (1.0, 2.0, "real words"))

        assert len(to_transcript(raw)) == 1

    def test_drops_segments_with_no_duration(self):
        raw = ((1.0, 1.0, "blip"), (1.0, 2.0, "real words"))

        assert len(to_transcript(raw)) == 1

    def test_keeps_the_order_it_was_given(self):
        raw = ((0.0, 1.0, "first"), (1.0, 2.0, "second"))

        assert [segment.text for segment in to_transcript(raw)] == ["first", "second"]

    def test_an_empty_result_yields_no_segments(self):
        assert to_transcript(()) == ()


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    if shutil.which("say") is None:
        pytest.skip("`say` is only available on macOS")

    from kov_worker.fixtures import Speaker, synthesize

    speaker = Speaker(
        "test",
        "Samantha",
        "The window was open and the street outside was busy all afternoon.",
    )
    path = tmp_path_factory.mktemp("speech") / "clean.wav"
    synthesize(speaker, path, 48_000)
    samples, _ = sf.read(path, dtype="float32", always_2d=False)
    return samples


@pytest.mark.slow
class TestAgainstRealSpeech:
    """The only evidence F4 does anything. Loads whisper and synthesises speech."""

    def test_recognises_the_words_that_were_spoken(self, speech):
        from kov_worker.transcribe import transcribe_samples

        segments = transcribe_samples(speech, 48_000)
        said = " ".join(segment.text for segment in segments).lower()

        hits = [word for word in ("window", "street", "afternoon") if word in said]
        assert len(hits) >= 2, f"whisper heard: {said!r}"

    def test_reports_timings_inside_the_track(self, speech):
        from kov_worker.transcribe import transcribe_samples

        duration_ms = round(len(speech) / 48_000 * 1_000)
        segments = transcribe_samples(speech, 48_000)

        assert segments
        assert all(0 <= segment.start_ms < segment.end_ms for segment in segments)
        assert max(segment.end_ms for segment in segments) <= duration_ms + 1_000

    def test_silence_produces_no_words(self):
        from kov_worker.transcribe import transcribe_samples

        segments = transcribe_samples(np.zeros(48_000 * 2, dtype=np.float32), 48_000)

        assert segments == ()


class TestConfiguration:
    def test_runs_at_sixteen_kilohertz(self):
        assert WHISPER_SAMPLE_RATE == 16_000

    def test_defaults_to_a_small_model(self):
        assert DEFAULT_WHISPER_MODEL == "base"

    def test_an_unknown_model_size_is_rejected_before_downloading(self, monkeypatch):
        monkeypatch.setenv("KOV_WHISPER_MODEL", "gigantic")

        from kov_worker import transcribe

        monkeypatch.setattr(transcribe, "_model", None)

        with pytest.raises(TranscribeError, match="gigantic"):
            transcribe.transcribe_samples(np.zeros(1_000, dtype=np.float32), 48_000)

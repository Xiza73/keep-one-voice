import math

import numpy as np
import pytest
import soundfile as sf

from kov_worker.stages import StageError, run_stages


@pytest.fixture
def tone(tmp_path):
    """A one second 440 Hz mono tone at 16 kHz, written as a real WAV file."""
    sample_rate = 16_000
    t = np.linspace(0.0, 1.0, sample_rate, endpoint=False)
    samples = (0.25 * np.sin(2 * math.pi * 440.0 * t)).astype(np.float32)

    path = tmp_path / "tone.wav"
    sf.write(path, samples, sample_rate)
    return path


def halve(samples, _sample_rate):
    return (samples * 0.5).astype(np.float32)


def silence(samples, _sample_rate):
    return np.zeros_like(samples)


class TestRunStages:
    def test_writes_an_output_file(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("separate",), implementations={})

        assert output.exists()

    def test_preserves_sample_rate_and_channel_count(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("separate",), implementations={})

        info = sf.info(str(output))
        assert info.samplerate == 16_000
        assert info.channels == 1

    def test_passes_audio_through_a_stage_that_has_no_implementation(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("separate",), implementations={})

        original, _ = sf.read(str(tone), dtype="float32")
        produced, _ = sf.read(str(output), dtype="float32")
        assert np.allclose(original, produced, atol=1e-4)

    def test_warns_once_per_unimplemented_stage(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        result = run_stages(str(tone), str(output), ("separate", "diarize"), implementations={})

        assert len(result.warnings) == 2
        assert any("separate" in warning for warning in result.warnings)
        assert any("diarize" in warning for warning in result.warnings)

    def test_applies_a_stage_that_has_an_implementation(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("denoise",), implementations={"denoise": halve})

        original, _ = sf.read(str(tone), dtype="float32")
        produced, _ = sf.read(str(output), dtype="float32")
        assert np.allclose(produced, original * 0.5, atol=1e-3)

    def test_does_not_warn_about_an_implemented_stage(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        result = run_stages(
            str(tone), str(output), ("denoise",), implementations={"denoise": halve}
        )

        assert result.warnings == ()

    def test_runs_stages_in_the_requested_order(self, tone, tmp_path):
        seen = []

        def first(samples, _sr):
            seen.append("first")
            return samples

        def second(samples, _sr):
            seen.append("second")
            return samples

        run_stages(
            str(tone),
            str(tmp_path / "out.wav"),
            ("denoise", "separate"),
            implementations={"denoise": first, "separate": second},
        )

        assert seen == ["first", "second"]

    def test_chains_the_output_of_one_stage_into_the_next(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(
            str(tone),
            str(output),
            ("denoise", "separate"),
            implementations={"denoise": halve, "separate": halve},
        )

        original, _ = sf.read(str(tone), dtype="float32")
        produced, _ = sf.read(str(output), dtype="float32")
        assert np.allclose(produced, original * 0.25, atol=1e-3)

    def test_wraps_a_failing_stage_in_a_stage_error_that_names_it(self, tone, tmp_path):
        def explode(_samples, _sr):
            raise RuntimeError("model weights are corrupt")

        with pytest.raises(StageError, match="denoise"):
            run_stages(
                str(tone),
                str(tmp_path / "out.wav"),
                ("denoise",),
                implementations={"denoise": explode},
            )

    def test_reports_the_duration_it_read(self, tone, tmp_path):
        result = run_stages(str(tone), str(tmp_path / "out.wav"), ("separate",), implementations={})

        assert result.duration_ms == pytest.approx(1_000, abs=2)

    def test_returns_no_segments_while_diarization_is_unimplemented(self, tone, tmp_path):
        result = run_stages(str(tone), str(tmp_path / "out.wav"), ("diarize",), implementations={})

        assert result.segments == ()

    def test_raises_a_stage_error_when_the_input_is_missing(self, tmp_path):
        with pytest.raises(StageError, match="unreadable-input"):
            run_stages(
                str(tmp_path / "nope.wav"),
                str(tmp_path / "out.wav"),
                ("separate",),
                implementations={},
            )

    def test_raises_a_stage_error_when_the_input_is_not_audio(self, tmp_path):
        junk = tmp_path / "junk.wav"
        junk.write_bytes(b"this is definitely not a wav file")

        with pytest.raises(StageError, match="unreadable-input"):
            run_stages(str(junk), str(tmp_path / "out.wav"), ("separate",), implementations={})

    def test_rejects_a_stage_that_returns_silence(self, tone, tmp_path):
        with pytest.raises(StageError, match="silent"):
            run_stages(
                str(tone),
                str(tmp_path / "out.wav"),
                ("denoise",),
                implementations={"denoise": silence},
            )

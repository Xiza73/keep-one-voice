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


class TestRunStages:
    def test_writes_an_output_file(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("denoise",))

        assert output.exists()

    def test_preserves_sample_rate_and_channel_count(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("denoise",))

        info = sf.info(str(output))
        assert info.samplerate == 16_000
        assert info.channels == 1

    def test_preserves_the_samples_while_stages_are_unimplemented(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        run_stages(str(tone), str(output), ("denoise",))

        original, _ = sf.read(str(tone), dtype="float32")
        produced, _ = sf.read(str(output), dtype="float32")
        assert np.allclose(original, produced, atol=1e-4)

    def test_warns_once_per_unimplemented_stage(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        result = run_stages(str(tone), str(output), ("denoise", "separate"))

        assert len(result.warnings) == 2
        assert any("denoise" in warning for warning in result.warnings)
        assert any("separate" in warning for warning in result.warnings)

    def test_reports_the_duration_it_read(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        result = run_stages(str(tone), str(output), ("denoise",))

        assert result.duration_ms == pytest.approx(1_000, abs=2)

    def test_returns_no_segments_while_diarization_is_unimplemented(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        result = run_stages(str(tone), str(output), ("diarize",))

        assert result.segments == ()

    def test_raises_a_stage_error_when_the_input_is_missing(self, tmp_path):
        with pytest.raises(StageError, match="unreadable-input"):
            run_stages(str(tmp_path / "nope.wav"), str(tmp_path / "out.wav"), ("denoise",))

    def test_raises_a_stage_error_when_the_input_is_not_audio(self, tmp_path):
        junk = tmp_path / "junk.wav"
        junk.write_bytes(b"this is definitely not a wav file")

        with pytest.raises(StageError, match="unreadable-input"):
            run_stages(str(junk), str(tmp_path / "out.wav"), ("denoise",))

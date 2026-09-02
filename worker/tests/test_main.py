"""Protocol-level tests for the worker entry point.

Every stage now has an implementation, so there is no longer an "unimplemented"
stage to lean on. These use `extract`, which is deliberately model-free: given
segments and a speaker it is pure masking, so the protocol path is exercised end
to end without loading a model, a token or a network.
"""

import json
import math

import numpy as np
import pytest
import soundfile as sf

from kov_worker.__main__ import handle


@pytest.fixture
def tone(tmp_path):
    sample_rate = 16_000
    t = np.linspace(0.0, 1.0, sample_rate, endpoint=False)
    samples = (0.25 * np.sin(2 * math.pi * 440.0 * t)).astype(np.float32)

    path = tmp_path / "tone.wav"
    sf.write(path, samples, sample_rate)
    return path


def request_line(**overrides):
    payload = {
        "id": "req-1",
        "input_path": "in.wav",
        "output_path": "out.wav",
        "stages": ["extract"],
        "segments": [
            {"speaker_id": "SPEAKER_00", "start_ms": 0, "end_ms": 800, "mean_dbfs": -20.0}
        ],
        "speaker": "SPEAKER_00",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestHandle:
    def test_answers_a_valid_request_with_the_same_id(self, tone, tmp_path):
        response = handle(request_line(input_path=str(tone), output_path=str(tmp_path / "o.wav")))

        assert response.id == "req-1"
        assert response.ok is True

    def test_produces_the_output_file(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        handle(request_line(input_path=str(tone), output_path=str(output)))

        assert output.exists()

    def test_echoes_the_segments_it_was_given(self, tone, tmp_path):
        response = handle(request_line(input_path=str(tone), output_path=str(tmp_path / "o.wav")))

        assert len(response.segments) == 1
        assert response.segments[0].speaker_id == "SPEAKER_00"

    def test_answers_a_malformed_line_with_a_protocol_error(self):
        response = handle("{not json")

        assert response.ok is False
        assert response.error is not None
        assert response.error["kind"] == "protocol"

    def test_answers_an_unreadable_input_with_a_stage_error(self, tmp_path):
        response = handle(
            request_line(
                input_path=str(tmp_path / "missing.wav"),
                output_path=str(tmp_path / "out.wav"),
            )
        )

        assert response.ok is False
        assert response.error is not None
        assert response.error["kind"] == "unreadable-input"

    def test_keeps_the_request_id_on_a_stage_error(self, tmp_path):
        response = handle(
            request_line(
                id="req-42",
                input_path=str(tmp_path / "missing.wav"),
                output_path=str(tmp_path / "out.wav"),
            )
        )

        assert response.id == "req-42"

    def test_extract_without_a_speaker_reports_which_stage_failed(self, tone, tmp_path):
        response = handle(
            request_line(
                input_path=str(tone),
                output_path=str(tmp_path / "out.wav"),
                speaker=None,
            )
        )

        assert response.ok is False
        assert response.error is not None
        assert response.error["kind"] == "no-speaker-chosen"
        assert response.error["stage"] == "extract"

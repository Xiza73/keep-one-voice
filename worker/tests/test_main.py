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
    # `separate` is deliberately unimplemented: these tests are about the
    # protocol, and must not drag a model into a unit test.
    payload = {
        "id": "req-1",
        "input_path": "in.wav",
        "output_path": "out.wav",
        "stages": ["separate"],
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestHandle:
    def test_answers_a_valid_request_with_the_same_id(self, tone, tmp_path):
        response = handle(request_line(input_path=str(tone), output_path=str(tmp_path / "out.wav")))

        assert response.id == "req-1"
        assert response.ok is True

    def test_produces_the_output_file(self, tone, tmp_path):
        output = tmp_path / "out.wav"

        handle(request_line(input_path=str(tone), output_path=str(output)))

        assert output.exists()

    def test_reports_warnings_for_unimplemented_stages(self, tone, tmp_path):
        response = handle(
            request_line(
                input_path=str(tone),
                output_path=str(tmp_path / "out.wav"),
                stages=["separate", "diarize"],
            )
        )

        assert len(response.warnings) == 2

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

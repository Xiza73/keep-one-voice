import json

import pytest

from kov_worker.protocol import (
    ProtocolError,
    Response,
    SpeakerSegment,
    parse_request,
    serialize_response,
)


def valid_payload(**overrides):
    payload = {
        "id": "req-1",
        "input_path": "decoded.wav",
        "output_path": "interview.clean.wav",
        "stages": ["denoise", "extract"],
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestParseRequest:
    def test_parses_a_valid_request(self):
        request = parse_request(valid_payload())

        assert request.id == "req-1"
        assert request.input_path == "decoded.wav"
        assert request.stages == ("denoise", "extract")

    def test_rejects_malformed_json(self):
        with pytest.raises(ProtocolError, match="invalid JSON"):
            parse_request("{not json")

    def test_rejects_a_non_object_payload(self):
        with pytest.raises(ProtocolError, match="must be a JSON object"):
            parse_request("[1, 2, 3]")

    @pytest.mark.parametrize("missing", ["id", "input_path", "output_path", "stages"])
    def test_rejects_a_missing_field(self, missing):
        payload = json.loads(valid_payload())
        del payload[missing]

        with pytest.raises(ProtocolError, match=f"missing field: {missing}"):
            parse_request(json.dumps(payload))

    def test_rejects_an_empty_stage_list(self):
        with pytest.raises(ProtocolError, match="non-empty array"):
            parse_request(valid_payload(stages=[]))

    def test_rejects_an_unknown_stage(self):
        with pytest.raises(ProtocolError, match="unknown stage"):
            parse_request(valid_payload(stages=["denoise", "transcribe"]))

    def test_rejects_decode_because_it_runs_in_the_cli(self):
        with pytest.raises(ProtocolError, match="unknown stage"):
            parse_request(valid_payload(stages=["decode"]))


class TestSerializeResponse:
    def test_serializes_a_successful_response(self):
        response = Response(
            id="req-1",
            ok=True,
            output_path="interview.clean.wav",
            segments=(SpeakerSegment("SPEAKER_00", 0, 1_500, -21.4),),
            warnings=('stage "denoise" is not implemented yet',),
        )

        payload = json.loads(serialize_response(response))

        assert payload["ok"] is True
        assert payload["output_path"] == "interview.clean.wav"
        assert payload["warnings"] == ['stage "denoise" is not implemented yet']
        assert payload["segments"] == [
            {
                "speaker_id": "SPEAKER_00",
                "start_ms": 0,
                "end_ms": 1_500,
                "mean_dbfs": -21.4,
            }
        ]

    def test_serializes_an_error_response(self):
        response = Response(id="req-1", ok=False, error={"kind": "model-gated"})

        payload = json.loads(serialize_response(response))

        assert payload["ok"] is False
        assert payload["error"] == {"kind": "model-gated"}
        assert "segments" not in payload

    def test_stays_on_a_single_line(self):
        response = Response(id="req-1", ok=True, output_path="out.wav")

        assert "\n" not in serialize_response(response)

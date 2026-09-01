"""Wire contract between the TypeScript CLI and this worker.

Transport is newline delimited JSON over stdio: one request per line on stdin,
one response per line on stdout. Logs go to stderr and never to stdout.

This module deliberately depends on the standard library only, so the contract
can be tested without installing the model stack.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Stage = Literal["decode", "denoise", "separate", "diarize", "extract"]

STAGES: tuple[Stage, ...] = ("decode", "denoise", "separate", "diarize", "extract")


class ProtocolError(ValueError):
    """Raised when an incoming payload does not satisfy the contract."""


@dataclass(frozen=True)
class Request:
    id: str
    input_path: str
    output_path: str
    stages: tuple[Stage, ...]


@dataclass(frozen=True)
class SpeakerSegment:
    speaker_id: str
    start_ms: int
    end_ms: int
    mean_dbfs: float


@dataclass(frozen=True)
class Response:
    id: str
    ok: bool
    output_path: str | None = None
    segments: tuple[SpeakerSegment, ...] = ()
    error: dict[str, Any] | None = field(default=None)


def parse_request(line: str) -> Request:
    """Parse one stdin line into a Request, or raise ProtocolError."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProtocolError("request must be a JSON object")

    for key in ("id", "input_path", "output_path", "stages"):
        if key not in payload:
            raise ProtocolError(f"missing field: {key}")

    raw_stages = payload["stages"]
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ProtocolError("stages must be a non-empty array")

    unknown = [stage for stage in raw_stages if stage not in STAGES]
    if unknown:
        raise ProtocolError(f"unknown stage(s): {', '.join(map(str, unknown))}")

    return Request(
        id=str(payload["id"]),
        input_path=str(payload["input_path"]),
        output_path=str(payload["output_path"]),
        stages=tuple(raw_stages),
    )


def serialize_response(response: Response) -> str:
    """Render a Response as a single stdout line."""
    payload: dict[str, Any] = {"id": response.id, "ok": response.ok}

    if response.ok:
        payload["output_path"] = response.output_path
        payload["segments"] = [
            {
                "speaker_id": segment.speaker_id,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "mean_dbfs": segment.mean_dbfs,
            }
            for segment in response.segments
        ]
    else:
        payload["error"] = response.error or {"kind": "unknown"}

    return json.dumps(payload, separators=(",", ":"))

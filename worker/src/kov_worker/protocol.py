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

Stage = Literal["denoise", "separate", "diarize", "extract"]

# `decode` is absent on purpose: FFmpeg is invoked from the CLI so that there is
# a single process-spawning surface to audit, and so an unreadable file fails
# before the model stack is ever imported.
STAGES: tuple[Stage, ...] = ("denoise", "separate", "diarize", "extract")


class ProtocolError(ValueError):
    """Raised when an incoming payload does not satisfy the contract."""


@dataclass(frozen=True)
class Request:
    id: str
    input_path: str
    output_path: str
    stages: tuple[Stage, ...]
    # Carried by the extract call: the CLI diarizes first, chooses in the domain
    # layer, then sends the result back for masking.
    segments: tuple[SpeakerSegment, ...] = ()
    speaker: str | None = None


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
    warnings: tuple[str, ...] = ()
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

    speaker = payload.get("speaker")

    return Request(
        id=str(payload["id"]),
        input_path=str(payload["input_path"]),
        output_path=str(payload["output_path"]),
        stages=tuple(raw_stages),
        segments=_parse_segments(payload.get("segments", [])),
        speaker=None if speaker is None else str(speaker),
    )


def _parse_segments(raw: Any) -> tuple[SpeakerSegment, ...]:
    if not isinstance(raw, list):
        raise ProtocolError("segments must be an array")

    parsed = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ProtocolError(f"segment {index} must be an object")

        missing = [
            key for key in ("speaker_id", "start_ms", "end_ms", "mean_dbfs") if key not in item
        ]
        if missing:
            raise ProtocolError(f"segment {index} is missing: {', '.join(missing)}")

        try:
            parsed.append(
                SpeakerSegment(
                    speaker_id=str(item["speaker_id"]),
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                    mean_dbfs=float(item["mean_dbfs"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ProtocolError(f"segment {index} has a non-numeric field: {exc}") from exc

    return tuple(parsed)


def serialize_response(response: Response) -> str:
    """Render a Response as a single stdout line."""
    payload: dict[str, Any] = {"id": response.id, "ok": response.ok}

    if response.ok:
        payload["output_path"] = response.output_path
        payload["warnings"] = list(response.warnings)
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

"""Entry point: read requests from stdin, write responses to stdout.

Logs must go to stderr. Anything printed to stdout that is not a protocol line
is noise the CLI has to skip past.
"""

from __future__ import annotations

import sys
from typing import Any

from kov_worker.protocol import (
    ProtocolError,
    Response,
    parse_request,
    serialize_response,
)
from kov_worker.stages import StageError, run_stages


def handle(line: str) -> Response:
    try:
        request = parse_request(line)
    except ProtocolError as exc:
        return Response(id="", ok=False, error={"kind": "protocol", "detail": str(exc)})

    try:
        result = run_stages(
            request.input_path,
            request.output_path,
            request.stages,
            segments=request.segments,
            speaker=request.speaker,
        )
    except StageError as exc:
        error: dict[str, Any] = {"kind": exc.kind, "detail": exc.detail}
        if exc.stage is not None:
            error["stage"] = exc.stage
        return Response(id=request.id, ok=False, error=error)

    return Response(
        id=request.id,
        ok=True,
        output_path=result.output_path,
        segments=result.segments,
        warnings=result.warnings,
    )


def main() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        sys.stdout.write(serialize_response(handle(line)) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

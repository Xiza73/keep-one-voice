"""Entry point: read requests from stdin, write responses to stdout."""

from __future__ import annotations

import sys

from kov_worker.protocol import ProtocolError, Response, parse_request, serialize_response


def handle(line: str) -> Response:
    try:
        request = parse_request(line)
    except ProtocolError as exc:
        return Response(id="", ok=False, error={"kind": "protocol", "detail": str(exc)})

    # TODO(F0): dispatch each stage to its implementation.
    return Response(
        id=request.id,
        ok=False,
        error={"kind": "not-implemented", "detail": f"stages: {', '.join(request.stages)}"},
    )


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        sys.stdout.write(serialize_response(handle(line)) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Audio stage execution.

Every stage is still unimplemented, so the worker passes the audio through
unchanged and reports one warning per requested stage. That is deliberate: it
proves the whole round trip end to end without pretending the audio was
processed.
"""

from __future__ import annotations

from dataclasses import dataclass

import soundfile as sf

from kov_worker.protocol import SpeakerSegment, Stage


class StageError(RuntimeError):
    """A failure the CLI can render and the user can act on."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


@dataclass(frozen=True)
class StageResult:
    output_path: str
    duration_ms: int
    segments: tuple[SpeakerSegment, ...]
    warnings: tuple[str, ...]


def run_stages(input_path: str, output_path: str, stages: tuple[Stage, ...]) -> StageResult:
    try:
        samples, sample_rate = sf.read(input_path, dtype="float32", always_2d=False)
    except Exception as exc:
        raise StageError("unreadable-input", str(exc)) from exc

    warnings = tuple(
        f'stage "{stage}" is not implemented yet; audio passed through unchanged'
        for stage in stages
    )

    try:
        sf.write(output_path, samples, sample_rate)
    except Exception as exc:
        raise StageError("write-failed", str(exc)) from exc

    duration_ms = round(len(samples) / sample_rate * 1_000) if sample_rate else 0

    return StageResult(
        output_path=output_path,
        duration_ms=duration_ms,
        segments=(),
        warnings=warnings,
    )

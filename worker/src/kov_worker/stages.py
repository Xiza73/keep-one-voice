"""Audio stage execution.

Stages are looked up in a registry rather than hard coded, so a phase that has
no implementation yet degrades to a pass-through with a warning instead of a
lie, and tests can exercise the dispatch without loading a model stack.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from kov_worker.protocol import SpeakerSegment, Stage

StageFn = Callable[[NDArray[np.float32], int], NDArray[np.float32]]


class StageError(RuntimeError):
    """A failure the CLI can render and the user can act on."""

    def __init__(self, kind: str, detail: str, stage: Stage | None = None) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail
        self.stage = stage


@dataclass(frozen=True)
class StageResult:
    output_path: str
    duration_ms: int
    segments: tuple[SpeakerSegment, ...]
    warnings: tuple[str, ...]


def default_implementations() -> dict[str, StageFn]:
    """The stages that actually do something today. F2 to F4 are still absent."""
    from kov_worker.denoise import denoise_samples

    return {"denoise": denoise_samples}


def run_stages(
    input_path: str,
    output_path: str,
    stages: tuple[Stage, ...],
    implementations: dict[str, StageFn] | None = None,
) -> StageResult:
    registry = default_implementations() if implementations is None else implementations

    try:
        samples, sample_rate = sf.read(input_path, dtype="float32", always_2d=False)
    except Exception as exc:
        raise StageError("unreadable-input", str(exc)) from exc

    had_signal = bool(np.any(samples))
    warnings: list[str] = []

    for stage in stages:
        run = registry.get(stage)

        if run is None:
            warnings.append(
                f'stage "{stage}" is not implemented yet; audio passed through unchanged'
            )
            continue

        try:
            samples = run(samples, sample_rate)
        except Exception as exc:
            raise StageError("stage-failed", f'stage "{stage}" failed: {exc}', stage) from exc

    if had_signal and not np.any(samples):
        raise StageError(
            "silent-output",
            f"the pipeline produced a silent track after: {', '.join(stages)}",
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
        warnings=tuple(warnings),
    )

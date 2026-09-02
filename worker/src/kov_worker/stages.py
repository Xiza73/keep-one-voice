"""Audio stage execution.

Stages are looked up in a registry rather than hard coded, so a phase with no
implementation degrades to a pass-through with a warning instead of a lie, and
dispatch stays testable without loading a model stack.

A stage takes audio plus context and returns audio plus, optionally, segments.
That shape exists because F3 needs both directions: `diarize` produces the
segments and `extract` consumes them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from kov_worker.protocol import SpeakerSegment, Stage


@dataclass(frozen=True)
class StageContext:
    sample_rate: int
    segments: tuple[SpeakerSegment, ...] = ()
    speaker: str | None = None


@dataclass(frozen=True)
class StageOutput:
    samples: NDArray[np.float32]
    segments: tuple[SpeakerSegment, ...] = ()


StageFn = Callable[[NDArray[np.float32], StageContext], StageOutput]


class StageError(RuntimeError):
    """A failure the CLI can render and the user can act on."""

    def __init__(self, kind: str, detail: str, stage: Stage | None = None) -> None:
        # The stage travels as its own field, so `detail` must not repeat it —
        # the CLI renders both and would print the name twice.
        label = f"{kind} in {stage}" if stage else kind
        super().__init__(f"{label}: {detail}")
        self.kind = kind
        self.detail = detail
        self.stage = stage


@dataclass(frozen=True)
class StageResult:
    output_path: str
    duration_ms: int
    segments: tuple[SpeakerSegment, ...]
    warnings: tuple[str, ...]


def _audio_only(fn: Callable[[NDArray[np.float32], int], NDArray[np.float32]]) -> StageFn:
    """Adapt a plain audio transform to the stage contract."""

    def run(samples: NDArray[np.float32], context: StageContext) -> StageOutput:
        return StageOutput(samples=fn(samples, context.sample_rate))

    return run


def _denoise(samples: NDArray[np.float32], context: StageContext) -> StageOutput:
    from kov_worker.denoise import denoise_samples

    return _audio_only(denoise_samples)(samples, context)


def _separate(samples: NDArray[np.float32], context: StageContext) -> StageOutput:
    from kov_worker.separate import separate_samples

    return _audio_only(separate_samples)(samples, context)


def _diarize(samples: NDArray[np.float32], context: StageContext) -> StageOutput:
    from kov_worker.diarize import diarize_samples

    # Diarization reports timestamps; it must not touch the audio.
    return StageOutput(
        samples=samples,
        segments=diarize_samples(samples, context.sample_rate),
    )


def _extract(samples: NDArray[np.float32], context: StageContext) -> StageOutput:
    from kov_worker.extract import extract_speaker

    if context.speaker is None:
        raise StageError(
            "no-speaker-chosen",
            "extract needs a speaker; run diarize first or pass one explicitly",
            "extract",
        )

    return StageOutput(
        samples=extract_speaker(samples, context.sample_rate, context.segments, context.speaker)
    )


def default_implementations() -> dict[str, StageFn]:
    return {
        "denoise": _denoise,
        "separate": _separate,
        "diarize": _diarize,
        "extract": _extract,
    }


def run_stages(
    input_path: str,
    output_path: str,
    stages: tuple[Stage, ...],
    implementations: dict[str, StageFn] | None = None,
    segments: tuple[SpeakerSegment, ...] = (),
    speaker: str | None = None,
) -> StageResult:
    registry = default_implementations() if implementations is None else implementations

    try:
        samples, sample_rate = sf.read(input_path, dtype="float32", always_2d=False)
    except Exception as exc:
        raise StageError("unreadable-input", str(exc)) from exc

    had_signal = bool(np.any(samples))
    context = StageContext(sample_rate=sample_rate, segments=segments, speaker=speaker)
    warnings: list[str] = []

    for stage in stages:
        run = registry.get(stage)

        if run is None:
            warnings.append(
                f'stage "{stage}" is not implemented yet; audio passed through unchanged'
            )
            continue

        try:
            output = run(samples, context)
        except StageError:
            raise
        except Exception as exc:
            raise StageError("stage-failed", str(exc), stage) from exc

        samples = output.samples
        if output.segments:
            context = replace(context, segments=output.segments)

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
        segments=context.segments,
        warnings=tuple(warnings),
    )

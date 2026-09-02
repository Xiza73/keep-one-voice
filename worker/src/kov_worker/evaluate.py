"""Measure cleaning quality against the generated corpus.

Run it with no processed directory to get the baseline: how good the noisy files
already are. Any cleaning stage has to beat that number, and by how much is the
only honest way to compare two models.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from kov_worker.metrics import si_sdr

# A denoiser may return a handful of samples more or less than it was given.
# A gross mismatch means the wrong file, and silently truncating would hide it.
MAX_DRIFT_RATIO = 0.01
MIN_DRIFT_SAMPLES = 64


class EvalError(RuntimeError):
    """Raised when the corpus or a processed file cannot be evaluated."""


@dataclass(frozen=True)
class EvalRow:
    speaker: str
    noise: str
    snr_db: float
    baseline_si_sdr: float
    processed_si_sdr: float | None

    @property
    def improvement(self) -> float | None:
        if self.processed_si_sdr is None:
            return None
        return self.processed_si_sdr - self.baseline_si_sdr


@dataclass(frozen=True)
class Summary:
    noise: str
    count: int
    mean_baseline: float
    mean_improvement: float | None


def align(
    reference: NDArray[np.floating],
    estimate: NDArray[np.floating],
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Trim both signals to a common length, refusing an implausible mismatch."""
    longest = max(len(reference), len(estimate))
    drift = abs(len(reference) - len(estimate))
    tolerance = max(longest * MAX_DRIFT_RATIO, MIN_DRIFT_SAMPLES)

    if drift > tolerance:
        raise EvalError(
            f"length mismatch of {drift} samples is too large to be a rounding artefact; "
            "this is probably the wrong file"
        )

    shortest = min(len(reference), len(estimate))
    return reference[:shortest], estimate[:shortest]


def _read(path: Path) -> NDArray[np.float32]:
    if not path.exists():
        raise EvalError(f"not found: {path}")
    samples, _ = sf.read(path, dtype="float32", always_2d=False)
    return samples


def evaluate(root: Path, processed_dir: Path | None = None) -> tuple[EvalRow, ...]:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise EvalError(
            f"no manifest at {manifest_path}. Generate the corpus first: bun run fixtures"
        )

    manifest = json.loads(manifest_path.read_text())

    rows: list[EvalRow] = []
    for entry in manifest["entries"]:
        clean = _read(root / entry["clean"])
        noisy = _read(root / entry["noisy"])

        reference, degraded = align(clean, noisy)
        baseline = si_sdr(reference, degraded)

        processed_score: float | None = None
        if processed_dir is not None:
            candidate = _read(processed_dir / Path(entry["noisy"]).name)
            reference, cleaned = align(clean, candidate)
            processed_score = si_sdr(reference, cleaned)

        rows.append(
            EvalRow(
                speaker=entry["speaker"],
                noise=entry["noise"],
                snr_db=float(entry["snr_db"]),
                baseline_si_sdr=baseline,
                processed_si_sdr=processed_score,
            )
        )

    return tuple(rows)


def summarize(rows: tuple[EvalRow, ...]) -> tuple[Summary, ...]:
    """Group by noise kind, preserving the order the kinds first appeared."""
    order: list[str] = []
    grouped: dict[str, list[EvalRow]] = {}

    for row in rows:
        if row.noise not in grouped:
            order.append(row.noise)
            grouped[row.noise] = []
        grouped[row.noise].append(row)

    summaries: list[Summary] = []
    for noise in order:
        group = grouped[noise]
        gains = [
            row.improvement
            for row in group
            if row.improvement is not None and math.isfinite(row.improvement)
        ]
        summaries.append(
            Summary(
                noise=noise,
                count=len(group),
                mean_baseline=float(np.mean([row.baseline_si_sdr for row in group])),
                mean_improvement=float(np.mean(gains)) if gains else None,
            )
        )

    return tuple(summaries)


def _db(value: float | None) -> str:
    if value is None:
        return "     —"
    if math.isinf(value):
        return "    inf" if value > 0 else "   -inf"
    return f"{value:+7.2f}"


def format_table(rows: tuple[EvalRow, ...]) -> str:
    lines = [
        f"{'speaker':<12} {'noise':<7} {'snr':>5} {'baseline':>9} {'cleaned':>9} {'gain':>9}",
        "-" * 56,
    ]
    for row in rows:
        lines.append(
            f"{row.speaker:<12} {row.noise:<7} {row.snr_db:>5.0f} "
            f"{_db(row.baseline_si_sdr):>9} {_db(row.processed_si_sdr):>9} "
            f"{_db(row.improvement):>9}"
        )

    lines.append("")
    lines.append(f"{'by noise':<12} {'count':>7} {'baseline':>9} {'mean gain':>11}")
    lines.append("-" * 56)
    for summary in summarize(rows):
        lines.append(
            f"{summary.noise:<12} {summary.count:>7} "
            f"{_db(summary.mean_baseline):>9} {_db(summary.mean_improvement):>11}"
        )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="kov-eval",
        description="Score the corpus with SI-SDR, optionally against processed output.",
    )
    parser.add_argument("--corpus", type=Path, default=Path("../fixtures/generated"))
    parser.add_argument(
        "--processed",
        type=Path,
        default=None,
        help="Directory of cleaned files, named after the noisy ones.",
    )
    args = parser.parse_args()

    try:
        rows = evaluate(args.corpus.resolve(), args.processed)
    except EvalError as exc:
        print(f"error: {exc}")
        return 1

    print(format_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

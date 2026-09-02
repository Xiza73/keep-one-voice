"""Multi-speaker mixtures for F3.

A noise mixture needs one clean reference. A conversation needs more: every
speaker's own contribution to the timeline, who spoke when, and two different
answers to "which voice do we keep".

- `dominant` is what the automatic heuristic should choose: most speaking time,
  ties broken by level. It mirrors `dominantSpeakerSelector` in packages/core.
- `intended` is the voice a person actually wants.

They agree in the easy scenarios. Two scenarios exist precisely so they do not,
because the heuristic is documented as failing when the other person talks
longer or louder. Encoding that here means the failure gets measured instead of
discovered by a user.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FADE_MS = 5.0


class ConversationError(RuntimeError):
    """Raised when a conversation cannot be laid out or rendered."""


@dataclass(frozen=True)
class Turn:
    speaker: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Scenario:
    key: str
    order: tuple[str, ...]
    overlap: float
    gains_db: dict[str, float]
    intended: str


# Speaker keys come from DEFAULT_SPEAKERS in fixtures.py.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="two-clean",
        order=("en-female", "en-male", "en-female", "en-male", "en-female", "en-female"),
        overlap=0.0,
        gains_db={},
        intended="en-female",
    ),
    Scenario(
        key="two-overlap",
        order=("en-female", "en-male", "en-female", "en-male", "en-female", "en-female"),
        overlap=0.3,
        gains_db={},
        intended="en-female",
    ),
    Scenario(
        key="three-overlap",
        order=(
            "en-female",
            "en-male",
            "es-female",
            "en-female",
            "en-male",
            "en-female",
            "es-female",
            "en-female",
        ),
        overlap=0.3,
        gains_db={},
        intended="en-female",
    ),
    # The interlocutor talks twice as long as the person we want.
    Scenario(
        key="two-hard-duration",
        order=("en-female", "en-male", "en-male", "en-male", "en-male", "en-female"),
        overlap=0.2,
        gains_db={},
        intended="en-female",
    ),
    # Equal speaking time, but the interlocutor was closer to the microphone.
    Scenario(
        key="two-hard-loudness",
        order=("en-female", "en-male", "en-female", "en-male"),
        overlap=0.2,
        gains_db={"en-male": 6.0},
        intended="en-female",
    ),
)


def plan_turns(order: tuple[str, ...], turn_ms: int, overlap: float) -> tuple[Turn, ...]:
    """Lay turns on a timeline, each one `turn_ms` long, stepped by the overlap."""
    if not order:
        raise ConversationError("a conversation needs at least one turn")
    if not 0.0 <= overlap < 1.0:
        raise ConversationError(f"overlap must be within [0, 1), got {overlap}")

    step = round(turn_ms * (1.0 - overlap))

    return tuple(
        Turn(speaker=speaker, start_ms=index * step, end_ms=index * step + turn_ms)
        for index, speaker in enumerate(order)
    )


def dominant_speaker(turns: tuple[Turn, ...], gains_db: dict[str, float]) -> str:
    """Most total speaking time, ties broken by level. Mirrors the TypeScript port."""
    if not turns:
        raise ConversationError("a conversation with no turns has no dominant speaker")

    totals: dict[str, int] = {}
    first_seen: list[str] = []

    for turn in turns:
        if turn.speaker not in totals:
            totals[turn.speaker] = 0
            first_seen.append(turn.speaker)
        totals[turn.speaker] += max(0, turn.end_ms - turn.start_ms)

    winner = first_seen[0]
    best = (totals[winner], gains_db.get(winner, 0.0))

    for speaker in first_seen[1:]:
        score = (totals[speaker], gains_db.get(speaker, 0.0))
        if score > best:
            winner, best = speaker, score

    return winner


def _slice(source: NDArray[np.float64], offset: int, length: int) -> NDArray[np.float64]:
    """Take `length` samples from `offset`, wrapping around when the clip runs out."""
    if len(source) == 0:
        raise ConversationError("a speaker was given an empty clip")

    repeats = math.ceil((offset + length) / len(source))
    tiled = np.tile(source, max(1, repeats))
    return tiled[offset : offset + length]


def _fade(chunk: NDArray[np.float64], sample_rate: int) -> NDArray[np.float64]:
    """Raised-cosine ramps at both ends, so a turn boundary is not a click."""
    ramp = min(int(FADE_MS / 1_000.0 * sample_rate), len(chunk) // 2)
    if ramp <= 0:
        return chunk

    window = np.ones(len(chunk))
    rise = 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, ramp)))
    window[:ramp] = rise
    window[-ramp:] = rise[::-1]
    return chunk * window


def render(
    turns: tuple[Turn, ...],
    speech: dict[str, NDArray[np.float32]],
    sample_rate: int,
    gains_db: dict[str, float],
) -> tuple[NDArray[np.float32], dict[str, NDArray[np.float32]]]:
    """Build the mixture and every speaker's own contribution to it.

    A reference is what a perfect extractor would return: that speaker's audio
    on the shared timeline, silent wherever they are not talking.
    """
    if not turns:
        raise ConversationError("a conversation needs at least one turn")

    speakers = {turn.speaker for turn in turns}
    missing = sorted(speakers - set(speech))
    if missing:
        raise ConversationError(f"no audio for: {', '.join(missing)}")

    total = round(max(turn.end_ms for turn in turns) / 1_000.0 * sample_rate)
    references = {speaker: np.zeros(total, dtype=np.float64) for speaker in speakers}
    cursor = dict.fromkeys(speakers, 0)

    for turn in turns:
        start = round(turn.start_ms / 1_000.0 * sample_rate)
        length = min(round((turn.end_ms - turn.start_ms) / 1_000.0 * sample_rate), total - start)
        if length <= 0:
            continue

        source = np.asarray(speech[turn.speaker], dtype=np.float64)
        chunk = _fade(_slice(source, cursor[turn.speaker], length), sample_rate)
        cursor[turn.speaker] = (cursor[turn.speaker] + length) % len(source)

        gain = 10.0 ** (gains_db.get(turn.speaker, 0.0) / 20.0)
        references[turn.speaker][start : start + length] += gain * chunk

    mixture = np.sum(list(references.values()), axis=0)

    peak = float(np.max(np.abs(mixture)))
    if peak > 1.0:
        headroom = 0.99 / peak
        mixture = mixture * headroom
        references = {speaker: track * headroom for speaker, track in references.items()}

    return (
        mixture.astype(np.float32),
        {speaker: track.astype(np.float32) for speaker, track in references.items()},
    )

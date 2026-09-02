import itertools

import numpy as np
import pytest

from kov_worker.conversations import (
    SCENARIOS,
    ConversationError,
    Scenario,
    Turn,
    dominant_speaker,
    plan_turns,
    render,
)

SAMPLE_RATE = 48_000
TURN_MS = 1_000


def speech_for(keys, seconds=4.0):
    rng = np.random.default_rng(3)
    return {
        key: rng.normal(0.0, 0.2, int(seconds * SAMPLE_RATE)).astype(np.float32) for key in keys
    }


class TestPlanTurns:
    def test_creates_one_turn_per_entry_in_the_order(self):
        turns = plan_turns(("a", "b", "a"), TURN_MS, 0.0)

        assert len(turns) == 3
        assert [turn.speaker for turn in turns] == ["a", "b", "a"]

    def test_turns_do_not_overlap_when_the_overlap_is_zero(self):
        turns = plan_turns(("a", "b", "a"), TURN_MS, 0.0)

        for earlier, later in itertools.pairwise(turns):
            assert later.start_ms >= earlier.end_ms

    def test_overlap_shortens_the_step_between_turns(self):
        turns = plan_turns(("a", "b"), TURN_MS, 0.5)

        assert turns[1].start_ms == 500
        assert turns[0].end_ms == 1_000

    def test_every_turn_lasts_the_requested_time(self):
        turns = plan_turns(("a", "b", "c"), TURN_MS, 0.3)

        for turn in turns:
            assert turn.end_ms - turn.start_ms == TURN_MS

    def test_rejects_an_empty_order(self):
        with pytest.raises(ConversationError, match="at least one turn"):
            plan_turns((), TURN_MS, 0.0)

    def test_rejects_an_overlap_that_would_stack_every_turn(self):
        with pytest.raises(ConversationError, match="overlap"):
            plan_turns(("a", "b"), TURN_MS, 1.0)


class TestDominantSpeaker:
    def test_picks_the_speaker_with_the_most_total_time(self):
        turns = (Turn("a", 0, 1_000), Turn("b", 1_000, 2_000), Turn("a", 2_000, 3_000))

        assert dominant_speaker(turns, {}) == "a"

    def test_breaks_a_tie_by_level(self):
        turns = (Turn("a", 0, 1_000), Turn("b", 1_000, 2_000))

        assert dominant_speaker(turns, {"a": -6.0, "b": 0.0}) == "b"

    def test_a_single_speaker_is_dominant(self):
        assert dominant_speaker((Turn("a", 0, 500),), {}) == "a"

    def test_rejects_an_empty_conversation(self):
        with pytest.raises(ConversationError, match="no turns"):
            dominant_speaker((), {})


class TestRender:
    def test_the_mixture_is_the_sum_of_the_references(self):
        turns = plan_turns(("a", "b", "a"), TURN_MS, 0.3)
        mixture, references = render(turns, speech_for(("a", "b")), SAMPLE_RATE, {})

        total = sum(references.values())
        assert np.allclose(mixture, total, atol=1e-5)

    def test_every_reference_shares_the_mixture_length(self):
        turns = plan_turns(("a", "b", "a"), TURN_MS, 0.3)
        mixture, references = render(turns, speech_for(("a", "b")), SAMPLE_RATE, {})

        for track in references.values():
            assert len(track) == len(mixture)

    def test_a_reference_is_silent_outside_its_own_turns(self):
        turns = (Turn("a", 0, 1_000), Turn("b", 2_000, 3_000))
        _, references = render(turns, speech_for(("a", "b")), SAMPLE_RATE, {})

        # Sample 1.5 s in: nobody is speaking there.
        quiet = references["a"][int(1.5 * SAMPLE_RATE)]
        assert quiet == pytest.approx(0.0, abs=1e-6)

    def test_a_reference_carries_signal_inside_its_own_turns(self):
        turns = (Turn("a", 0, 1_000), Turn("b", 2_000, 3_000))
        _, references = render(turns, speech_for(("a", "b")), SAMPLE_RATE, {})

        middle = references["a"][int(0.5 * SAMPLE_RATE)]
        assert abs(middle) > 0.0

    def test_the_mixture_never_clips(self):
        turns = plan_turns(("a", "b", "a", "b"), TURN_MS, 0.5)
        mixture, _ = render(turns, speech_for(("a", "b")), SAMPLE_RATE, {})

        assert np.max(np.abs(mixture)) <= 1.0

    def test_a_negative_gain_makes_that_speaker_quieter(self):
        turns = (Turn("a", 0, 1_000), Turn("b", 1_000, 2_000))
        speech = speech_for(("a", "b"))

        _, loud = render(turns, speech, SAMPLE_RATE, {})
        _, quiet = render(turns, speech, SAMPLE_RATE, {"a": -12.0})

        assert np.max(np.abs(quiet["a"])) < np.max(np.abs(loud["a"]))

    def test_is_reproducible(self):
        turns = plan_turns(("a", "b"), TURN_MS, 0.2)
        speech = speech_for(("a", "b"))

        first, _ = render(turns, speech, SAMPLE_RATE, {})
        second, _ = render(turns, speech, SAMPLE_RATE, {})

        assert np.array_equal(first, second)

    def test_rejects_a_turn_for_a_speaker_with_no_audio(self):
        with pytest.raises(ConversationError, match="no audio"):
            render((Turn("ghost", 0, 500),), speech_for(("a",)), SAMPLE_RATE, {})


class TestScenarios:
    def by_key(self, key: str) -> Scenario:
        for scenario in SCENARIOS:
            if scenario.key == key:
                return scenario
        raise AssertionError(f"no scenario named {key}")

    def test_every_scenario_has_a_unique_key(self):
        keys = [scenario.key for scenario in SCENARIOS]

        assert len(set(keys)) == len(keys)

    def test_every_intended_speaker_actually_takes_a_turn(self):
        for scenario in SCENARIOS:
            assert scenario.intended in scenario.order

    def test_the_easy_scenarios_let_the_heuristic_win(self):
        for key in ("two-clean", "two-overlap", "three-overlap"):
            scenario = self.by_key(key)
            turns = plan_turns(scenario.order, TURN_MS, scenario.overlap)

            assert dominant_speaker(turns, scenario.gains_db) == scenario.intended

    def test_the_hard_scenarios_defeat_the_heuristic_on_purpose(self):
        """These encode the documented failure mode, so it is measured, not discovered."""
        for key in ("two-hard-duration", "two-hard-loudness"):
            scenario = self.by_key(key)
            turns = plan_turns(scenario.order, TURN_MS, scenario.overlap)

            assert dominant_speaker(turns, scenario.gains_db) != scenario.intended

    def test_at_least_one_scenario_has_three_speakers(self):
        assert any(len(set(scenario.order)) >= 3 for scenario in SCENARIOS)

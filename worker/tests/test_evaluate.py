import json
import math

import numpy as np
import pytest
import soundfile as sf

from kov_worker.evaluate import (
    EvalError,
    EvalRow,
    align,
    evaluate,
    evaluate_conversations,
    summarize,
)

SAMPLE_RATE = 16_000
RNG = np.random.default_rng(99)


def write_wav(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples.astype(np.float32), SAMPLE_RATE)


@pytest.fixture
def corpus(tmp_path):
    """A one-entry corpus: clean speech plus a noisy version at a known SNR."""
    clean = RNG.normal(0.0, 0.2, SAMPLE_RATE).astype(np.float32)
    noise = RNG.normal(0.0, 0.05, SAMPLE_RATE).astype(np.float32)

    write_wav(tmp_path / "clean" / "spk.wav", clean)
    write_wav(tmp_path / "noisy" / "spk_white_snr10.wav", clean + noise)

    manifest = {
        "sample_rate": SAMPLE_RATE,
        "seed": 1,
        "entries": [
            {
                "speaker": "spk",
                "noise": "white",
                "snr_db": 10.0,
                "clean": "clean/spk.wav",
                "noisy": "noisy/spk_white_snr10.wav",
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


class TestAlign:
    def test_leaves_equal_lengths_untouched(self):
        a, b = align(np.ones(10), np.zeros(10))

        assert len(a) == 10
        assert len(b) == 10

    def test_truncates_both_to_the_shorter_one(self):
        a, b = align(np.ones(10), np.zeros(7))

        assert len(a) == 7
        assert len(b) == 7

    def test_rejects_a_difference_too_large_to_be_a_rounding_artefact(self):
        with pytest.raises(EvalError, match="length"):
            align(np.ones(16_000), np.zeros(8_000))


class TestEvaluate:
    def test_measures_the_baseline_against_the_clean_reference(self, corpus):
        rows = evaluate(corpus)

        assert len(rows) == 1
        assert math.isfinite(rows[0].baseline_si_sdr)

    def test_the_baseline_is_close_to_the_requested_snr(self, corpus):
        rows = evaluate(corpus)

        assert rows[0].baseline_si_sdr == pytest.approx(12.0, abs=3.0)

    def test_reports_no_processed_score_without_a_processed_directory(self, corpus):
        rows = evaluate(corpus)

        assert rows[0].processed_si_sdr is None
        assert rows[0].improvement is None

    def test_scores_a_processed_file_when_one_is_given(self, corpus, tmp_path):
        clean, _ = sf.read(corpus / "clean" / "spk.wav", dtype="float32")
        processed = tmp_path / "out"
        write_wav(processed / "spk_white_snr10.wav", clean)

        rows = evaluate(corpus, processed)

        assert rows[0].processed_si_sdr == math.inf

    def test_improvement_is_the_gain_over_the_baseline(self, corpus, tmp_path):
        clean, _ = sf.read(corpus / "clean" / "spk.wav", dtype="float32")
        noise = RNG.normal(0.0, 0.01, len(clean)).astype(np.float32)
        processed = tmp_path / "out"
        write_wav(processed / "spk_white_snr10.wav", clean + noise)

        rows = evaluate(corpus, processed)

        assert rows[0].improvement is not None
        assert rows[0].improvement > 0.0

    def test_reports_a_missing_processed_file_instead_of_crashing(self, corpus, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(EvalError, match="not found"):
            evaluate(corpus, empty)

    def test_rejects_a_corpus_without_a_manifest(self, tmp_path):
        with pytest.raises(EvalError, match="manifest"):
            evaluate(tmp_path)


@pytest.fixture
def conversation_corpus(tmp_path):
    """Two speakers on one timeline, plus the ground truth about who is who."""
    wanted = RNG.normal(0.0, 0.2, SAMPLE_RATE).astype(np.float32)
    other = RNG.normal(0.0, 0.2, SAMPLE_RATE).astype(np.float32)

    write_wav(tmp_path / "conversations" / "chat_wanted.wav", wanted)
    write_wav(tmp_path / "conversations" / "chat_other.wav", other)
    write_wav(tmp_path / "conversations" / "chat.wav", wanted + other)

    manifest = {
        "sample_rate": SAMPLE_RATE,
        "seed": 1,
        "entries": [],
        "conversations": [
            {
                "key": "chat",
                "mixture": "conversations/chat.wav",
                "references": {
                    "wanted": "conversations/chat_wanted.wav",
                    "other": "conversations/chat_other.wav",
                },
                "dominant": "other",
                "intended": "wanted",
                "turns": [],
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


class TestEvaluateConversations:
    def test_scores_the_mixture_against_the_intended_speaker(self, conversation_corpus):
        rows = evaluate_conversations(conversation_corpus)

        assert len(rows) == 1
        assert math.isfinite(rows[0].baseline_si_sdr)

    def test_reports_when_the_heuristic_would_pick_the_wrong_voice(self, conversation_corpus):
        rows = evaluate_conversations(conversation_corpus)

        assert rows[0].intended == "wanted"
        assert rows[0].dominant == "other"
        assert rows[0].heuristic_agrees is False

    def test_reports_agreement_when_dominant_matches_intended(self, tmp_path):
        wanted = RNG.normal(0.0, 0.2, SAMPLE_RATE).astype(np.float32)
        write_wav(tmp_path / "conversations" / "solo_wanted.wav", wanted)
        write_wav(tmp_path / "conversations" / "solo.wav", wanted)
        (tmp_path / "manifest.json").write_text(
            json.dumps(
                {
                    "sample_rate": SAMPLE_RATE,
                    "seed": 1,
                    "entries": [],
                    "conversations": [
                        {
                            "key": "solo",
                            "mixture": "conversations/solo.wav",
                            "references": {"wanted": "conversations/solo_wanted.wav"},
                            "dominant": "wanted",
                            "intended": "wanted",
                            "turns": [],
                        }
                    ],
                }
            )
        )

        rows = evaluate_conversations(tmp_path)

        assert rows[0].heuristic_agrees is True

    def test_scores_a_processed_file_when_one_is_given(self, conversation_corpus, tmp_path):
        wanted, _ = sf.read(
            conversation_corpus / "conversations" / "chat_wanted.wav", dtype="float32"
        )
        processed = tmp_path / "out"
        write_wav(processed / "chat.wav", wanted)

        rows = evaluate_conversations(conversation_corpus, processed)

        assert rows[0].processed_si_sdr == math.inf
        assert rows[0].improvement is not None

    def test_reports_a_missing_processed_file_instead_of_crashing(
        self, conversation_corpus, tmp_path
    ):
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(EvalError, match="not found"):
            evaluate_conversations(conversation_corpus, empty)

    def test_returns_nothing_for_a_corpus_without_conversations(self, corpus):
        assert evaluate_conversations(corpus) == ()

    def test_rejects_a_corpus_without_a_manifest(self, tmp_path):
        with pytest.raises(EvalError, match="manifest"):
            evaluate_conversations(tmp_path)


class TestSummarize:
    rows = (
        EvalRow("a", "white", 0.0, 1.0, 5.0),
        EvalRow("a", "white", 10.0, 3.0, 9.0),
        EvalRow("a", "hum", 0.0, 2.0, 4.0),
    )

    def test_groups_by_noise_kind(self):
        summary = summarize(self.rows)

        assert {group.noise for group in summary} == {"white", "hum"}

    def test_averages_the_improvement_within_a_group(self):
        summary = {group.noise: group for group in summarize(self.rows)}

        assert summary["white"].mean_improvement == pytest.approx(5.0)
        assert summary["hum"].mean_improvement == pytest.approx(2.0)

    def test_counts_the_entries_in_a_group(self):
        summary = {group.noise: group for group in summarize(self.rows)}

        assert summary["white"].count == 2

    def test_reports_no_improvement_when_nothing_was_processed(self):
        summary = summarize((EvalRow("a", "white", 0.0, 1.0, None),))

        assert summary[0].mean_improvement is None

    def test_ignores_infinite_scores_when_averaging(self):
        summary = summarize(
            (
                EvalRow("a", "white", 0.0, 1.0, math.inf),
                EvalRow("a", "white", 10.0, 3.0, 9.0),
            )
        )

        assert summary[0].mean_improvement == pytest.approx(6.0)

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

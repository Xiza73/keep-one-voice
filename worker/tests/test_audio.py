import io
import sys

import numpy as np
import pytest

from kov_worker.audio import fit_length, quiet_stdout, resample


class TestFitLength:
    def test_leaves_a_matching_length_untouched(self):
        samples = np.arange(10, dtype=np.float32)

        assert np.array_equal(fit_length(samples, 10), samples)

    def test_truncates_when_too_long(self):
        result = fit_length(np.arange(12, dtype=np.float32), 10)

        assert len(result) == 10
        assert result[-1] == 9.0

    def test_pads_with_silence_when_too_short(self):
        result = fit_length(np.ones(8, dtype=np.float32), 10)

        assert len(result) == 10
        assert result[-1] == 0.0
        assert result[7] == 1.0


class TestQuietStdout:
    def test_sends_stdout_to_stderr(self):
        out, errs = io.StringIO(), io.StringIO()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, errs
        try:
            with quiet_stdout():
                print("model chatter")
        finally:
            sys.stdout, sys.stderr = real_out, real_err

        assert out.getvalue() == ""
        assert "model chatter" in errs.getvalue()

    def test_restores_stdout_afterwards(self):
        before = sys.stdout

        with quiet_stdout():
            pass

        assert sys.stdout is before


class TestResample:
    def test_is_a_no_op_when_the_rates_match(self):
        samples = np.arange(100, dtype=np.float32)

        assert resample(samples, 48_000, 48_000) is samples

    def test_scales_the_sample_count_by_the_rate_ratio(self):
        pytest.importorskip("torchaudio", reason="needs a model extra installed")
        samples = np.zeros(48_000, dtype=np.float32)

        assert len(resample(samples, 48_000, 16_000)) == pytest.approx(16_000, abs=2)

    def test_round_trips_back_to_the_original_length(self):
        pytest.importorskip("torchaudio", reason="needs a model extra installed")
        samples = np.zeros(44_100, dtype=np.float32)

        there = resample(samples, 44_100, 48_000)
        back = resample(there, 48_000, 44_100)

        assert len(back) == pytest.approx(44_100, abs=4)

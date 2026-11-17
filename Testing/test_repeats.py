#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_repeats.py -- --repeat records are judged as one run, by their median
#
#   python3 -m unittest -v Testing/test_repeats.py
#
# Standard library only (drift.py is), so it runs on a bare runner.
#
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift  # noqa: E402


def record(seconds, run_id=None, repeat=None, version="6.2.1", memory=500.0):
    rec = {
        "test_name": "ex02_pvAnimation",
        "metrics_schema": 7,
        "execution_time": seconds,
        "memory_usage_mb": memory,
        "memory_measurement_scope": "child-tree-pss",
        "machine_info": {"paraview_version": version},
    }
    if run_id:
        rec["run_id"] = run_id
    if repeat:
        rec["repeat"] = {"index": repeat[0], "of": repeat[1]}
    return rec


class CollapseRepeats(unittest.TestCase):
    def test_single_runs_pass_through(self):
        history = {"2026-01-01T00": record(10.0, "a"), "2026-01-02T00": record(11.0)}
        self.assertEqual(drift.collapse_repeats(history), history)

    def test_repeats_fold_to_the_median_under_the_last_timestamp(self):
        history = {
            "2026-01-01T00": record(10.0, "old"),
            "2026-01-02T00:00": record(20.0, "r", (1, 3), memory=400.0),
            "2026-01-02T00:01": record(11.0, "r", (2, 3), memory=600.0),
            "2026-01-02T00:02": record(12.0, "r", (3, 3), memory=500.0),
        }
        folded = drift.collapse_repeats(history)
        self.assertEqual(list(folded), ["2026-01-01T00", "2026-01-02T00:02"])
        last = folded["2026-01-02T00:02"]
        self.assertEqual(last["execution_time"], 12.0)
        self.assertEqual(last["memory_usage_mb"], 500.0)
        self.assertEqual(last["repeat_values"]["execution_time"], [20.0, 11.0, 12.0])
        self.assertEqual(last["repeat"]["folded"], 3)
        # The original records are not changed.
        self.assertEqual(history["2026-01-02T00:02"]["execution_time"], 12.0)
        self.assertNotIn("repeat_values", history["2026-01-02T00:02"])

    def test_versions_in_one_run_id_fold_separately(self):
        history = {
            "t1": record(10.0, "bf", (1, 2), version="6.1.0"),
            "t2": record(12.0, "bf", (2, 2), version="6.1.0"),
            "t3": record(20.0, "bf", (1, 2), version="6.2.1"),
            "t4": record(22.0, "bf", (2, 2), version="6.2.1"),
        }
        folded = drift.collapse_repeats(history)
        self.assertEqual(sorted(folded), ["t2", "t4"])
        self.assertEqual(folded["t2"]["execution_time"], 11.0)
        self.assertEqual(folded["t4"]["execution_time"], 21.0)

    def test_drift_does_not_count_a_run_as_its_own_history(self):
        # Three earlier single runs near 10 s, then a repeated run near 30 s.
        history = {
            "2026-01-0{0}T00".format(day): record(10.0 + day * 0.1) for day in (1, 2, 3)
        }
        history.update(
            {
                "2026-01-05T00:0{0}".format(i): record(30.0 + i, "r", (i, 3))
                for i in (1, 2, 3)
            }
        )
        raw = drift.check_latest(history)
        folded = drift.collapse_repeats(history)
        judged = drift.check_latest(folded)
        # Unfolded, the last repeat sees its two siblings in its history.
        self.assertTrue(raw)
        self.assertEqual(raw[0]["history_runs"], 5)
        # Folded, the run is one value judged against the three earlier runs.
        self.assertEqual([w["metric"] for w in judged], ["execution_time"])
        self.assertEqual(judged[0]["history_runs"], 3)
        self.assertEqual(judged[0]["value"], 32.0)

    def test_failed_repeats_stay_out_of_the_median(self):
        failed = record(1.0, "r", (1, 3))
        failed["run_succeeded"] = False
        history = {
            "t1": failed,
            "t2": dict(record(10.0, "r", (2, 3)), run_succeeded=True),
            "t3": dict(record(12.0, "r", (3, 3)), run_succeeded=True),
        }
        folded = drift.collapse_repeats(history)["t3"]
        self.assertEqual(folded["execution_time"], 11.0)
        self.assertFalse(folded["run_succeeded"])

    def test_scoped_figures_fold_only_within_the_last_scope(self):
        other = record(10.0, "r", (1, 3), memory=9000.0)
        other["memory_measurement_scope"] = "child-tree-sampled"
        history = {
            "t1": other,
            "t2": record(11.0, "r", (2, 3), memory=400.0),
            "t3": record(12.0, "r", (3, 3), memory=600.0),
        }
        folded = drift.collapse_repeats(history)["t3"]
        self.assertEqual(folded["memory_usage_mb"], 500.0)
        self.assertEqual(folded["repeat_values"]["memory_usage_mb"], [400.0, 600.0])
        self.assertEqual(folded["memory_measurement_scope"], "child-tree-pss")
        # Wall time has no scope: every repeat counts.
        self.assertEqual(folded["execution_time"], 11.0)


if __name__ == "__main__":
    unittest.main()

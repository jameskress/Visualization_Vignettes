"""Tests for speed_index.py: the every-machine, every-version grid."""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speed_index  # noqa: E402


def rec(seconds, version, rev=1, **extra):
    out = {
        "execution_time": seconds,
        "machine_info": {"paraview_version": version},
        "metrics_schema": 8,
        "_rev": rev,
    }
    out.update(extra)
    return out


def ts(day, n=0):
    return "2026-11-{0:02d}T10:00:{1:02d}".format(day, n)


def build(histories, until=datetime.datetime(2026, 11, 24)):
    return speed_index.build(
        histories,
        "ParaView",
        set(),
        lambda r: True,
        lambda v: tuple(int(p) for p in v.split(".")),
        lambda c: c,
        until,
    )


class TypicalRun(unittest.TestCase):
    def test_reference_is_the_median_of_pair_medians_and_stays_fixed(self):
        """A run after the cut-off does not move the typical run."""
        h = {
            ("a", "ParaView"): {
                "ex01_x": [
                    (ts(10, i), rec(s, "6.2.1")) for i, s in enumerate((2, 2, 2))
                ]
            },
            ("b", "ParaView"): {
                "ex01_x": [
                    (ts(10, i), rec(s, "6.2.1")) for i, s in enumerate((4, 4, 4))
                ]
            },
            ("c", "ParaView"): {
                "ex01_x": [
                    (ts(10, i), rec(s, "6.2.1")) for i, s in enumerate((6, 6, 6))
                ]
                + [(ts(25, i), rec(100, "6.2.1")) for i in range(3)]
            },
        }
        data = build(h)
        m = data["measures"]["execution_time"]
        self.assertEqual(m["refs"]["ex01_x"], 4.0)
        self.assertEqual(m["moving"], [])
        self.assertEqual(data["until"], "23 Nov 2026")

    def test_a_vignette_with_no_record_before_the_cutoff_is_flagged(self):
        h = {("a", "ParaView"): {"ex01_x": [(ts(25), rec(3, "6.2.1"))]}}
        m = build(h)["measures"]["execution_time"]
        self.assertEqual(m["moving"], ["ex01_x"])
        self.assertEqual(m["refs"]["ex01_x"], 3.0)

    def test_only_the_newest_code_counts(self):
        h = {
            ("a", "ParaView"): {
                "ex01_x": [
                    (ts(10), rec(50, "6.2.1", rev=1)),
                    (ts(11), rec(2, "6.2.1", rev=2)),
                ]
            }
        }
        m = build(h)["measures"]["execution_time"]
        self.assertEqual(m["refs"]["ex01_x"], 2.0)


class Cells(unittest.TestCase):
    def history(self, slow_runs):
        """Machine a is the reference; b runs ex01 at slow_runs, ex02 at 2 s."""
        h = {}
        for config, ex01 in (("a", (2.0, 2.0, 2.0)), ("b", slow_runs)):
            h[(config, "ParaView")] = {
                "ex01_x": [(ts(10, i), rec(s, "6.2.1")) for i, s in enumerate(ex01)],
                "ex02_y": [(ts(10, i), rec(2.0, "6.2.1")) for i in range(len(ex01))],
            }
        return h

    def cell(self, data, config, version="6.2.1"):
        cells = data["measures"]["execution_time"]["cells"]
        return next(c for c in cells if c["c"] == config and c["v"] == version)

    def test_index_is_the_geometric_mean_of_ratios(self):
        # References: ex01 median of (2, 8) = 5, ex02 2. b: (8/5 * 2/2) ** 0.5.
        b = self.cell(build(self.history((8.0, 8.0, 8.0))), "b")
        self.assertAlmostEqual(b["i"], (8 / 5) ** 0.5, places=3)

    def test_steady_runs_have_a_tight_range_and_one_run_has_none(self):
        steady = self.cell(build(self.history((8.0, 8.0, 8.0))), "b")
        self.assertAlmostEqual(steady["lo"], steady["hi"], places=3)
        single = self.cell(build(self.history((8.0,))), "b")
        self.assertIsNone(single["lo"])

    def test_a_row_is_averaged_over_its_newest_versions_vignettes(self):
        h = self.history((2.0, 2.0, 2.0))
        # b at an older version ran only ex01: marked, over 1 of 2.
        h[("b", "ParaView")]["ex01_x"].append((ts(5), rec(2.0, "6.1.0")))
        old = self.cell(build(h), "b", "6.1.0")
        self.assertEqual((old["n"], old["of"]), (1, 2))
        # The newest version's vignettes set the row, and its cell has all.
        new = self.cell(build(h), "b", "6.2.1")
        self.assertEqual((new["n"], new["of"]), (2, 2))


class Colour(unittest.TestCase):
    def test_coloured_only_beyond_the_noise(self):
        c = speed_index.colour
        self.assertEqual(c(1.3, 1.2, 1.4), "slow2")
        self.assertEqual(c(1.1, 1.05, 1.15), "slow1")
        self.assertEqual(c(0.9, 0.85, 0.95), "fast1")
        self.assertEqual(c(0.7, 0.6, 0.75), "fast2")
        # The range covers 1x: within the noise.
        self.assertEqual(c(1.3, 0.9, 1.6), "")
        # Beyond the noise but under 5%: not coloured either.
        self.assertEqual(c(1.03, 1.02, 1.04), "")
        # One run per vignette: noise unknown.
        self.assertEqual(c(1.3, None, None), "one")


class Memory(unittest.TestCase):
    def test_only_pss_memory_counts(self):
        h = {
            ("a", "ParaView"): {
                "ex01_x": [
                    (
                        ts(10, 0),
                        rec(
                            2,
                            "6.2.1",
                            memory_usage_mb=500.0,
                            memory_measurement_scope="slurm-steps-plus-local-tree",
                        ),
                    ),
                    (
                        ts(10, 1),
                        rec(
                            2,
                            "6.2.1",
                            memory_usage_mb=400.0,
                            memory_measurement_scope="child-tree-pss",
                        ),
                    ),
                ]
            }
        }
        m = build(h)["measures"]["memory_usage_mb"]
        self.assertEqual(m["refs"]["ex01_x"], 400.0)


if __name__ == "__main__":
    unittest.main()

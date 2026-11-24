#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_dashboard_redesign.py -- the upgrade table's statistics, system
# changes and the run-number charts of the redesigned dashboard (#106)
#
#   python3 -m unittest -v Testing/test_dashboard_redesign.py
#
# Author: James Kress, <james@jameskress.com>

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402


class WelchAndClasses(unittest.TestCase):
    def test_welch_p_matches_known_values(self):
        # scipy.stats.ttest_ind(a, b, equal_var=False).pvalue for these
        # samples: 0.0058972389975785406 and 1.8928880423847155e-06.
        a = [10.0, 10.4, 10.2]
        b = [11.0, 11.5, 11.2]
        self.assertAlmostEqual(dashboard.welch_p(a, b), 0.0058972389975785, places=10)
        self.assertAlmostEqual(
            dashboard.welch_p([60.0, 60.5, 59.8], [40.0, 40.3, 39.9]),
            1.8928880423847155e-06,
            places=12,
        )
        self.assertAlmostEqual(dashboard.welch_p([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)
        self.assertIsNone(dashboard.welch_p([1.0], [1.0, 2.0]))
        self.assertEqual(dashboard.welch_p([2.0, 2.0], [3.0, 3.0]), 0.0)

    def test_change_class(self):
        cls = dashboard.change_class
        self.assertEqual(cls(-0.30, 0.01), "fast2")
        self.assertEqual(cls(-0.15, 0.01), "fast1")
        self.assertEqual(cls(0.12, 0.01), "slow1")
        self.assertEqual(cls(0.25, 0.01), "slow2")
        # Under 10% or not significant: printed, never coloured.
        self.assertEqual(cls(0.08, 0.001), "noise")
        self.assertEqual(cls(0.40, 0.20), "noise")
        self.assertEqual(cls(0.40, None), "one")

    def test_pct_uses_a_real_minus(self):
        self.assertEqual(dashboard.pct(-0.153), "−15%")
        self.assertEqual(dashboard.pct(0.12), "+12%")
        self.assertEqual(dashboard.pct(0.001), "0%")


def record(ts_run, kernel, version="6.2.1", seconds=10.0, gpu=None):
    info = {"release": kernel, "os_release": "Rocky 9.4", "paraview_version": version}
    if gpu:
        info["gpus"] = [{"name": "A100", "driver": gpu}]
    return {
        "run_id": ts_run,
        "machine_info": info,
        "execution_time": seconds,
        "run_succeeded": True,
    }


class SystemChanges(unittest.TestCase):
    def test_changes_are_per_run_and_only_real_ones(self):
        rows = {
            "ex00_pvQuery": [
                ("2026-10-01T10:00:00", record("r1", "5.14")),
                ("2026-10-08T10:00:00", record("r2", "5.14", gpu="570")),
                ("2026-11-01T10:00:00", record("r3", "6.4", gpu="575")),
            ],
            "ex01_pvScreenshot": [
                ("2026-11-01T10:05:00", record("r3", "6.4", gpu="575")),
            ],
        }
        changes = dashboard.platform_changes(rows)
        # The first GPU driver seen is not a change; one entry per run.
        self.assertEqual(len(changes), 1)
        ts, what = changes[0]
        self.assertEqual(ts, "2026-11-01T10:00:00")
        self.assertIn(("kernel", "5.14", "6.4"), what)
        self.assertIn(("GPU driver", "570", "575"), what)

    def test_a_change_in_the_second_tool_of_a_shared_run_counts(self):
        # ParaView and VisIt share run id r2; only VisIt's record, later in
        # the run, shows the new kernel.
        rows = {
            ("ParaView", "ex00_pvQuery"): [
                ("2026-10-01T10:00:00", record("r1", "5.14")),
                ("2026-11-01T10:00:00", record("r2", "5.14")),
            ],
            ("VisIt", "ex00_visitQuery"): [
                ("2026-10-01T11:00:00", record("r1", "5.14")),
                ("2026-11-01T12:00:00", record("r2", "6.4")),
            ],
        }
        changes = dashboard.platform_changes(rows)
        self.assertEqual(
            changes, [("2026-11-01T10:00:00", [("kernel", "5.14", "6.4")])]
        )

    def test_run_chart_marks_the_first_run_after_a_change(self):
        # The change is dated by another vignette's record (10:00); this
        # vignette ran at 10:05 in the same run.
        points = [
            ("2026-10-01T10:05:00", "6.2.1", 10.0, ""),
            ("2026-11-01T10:05:00", "6.2.1", 12.0, ""),
        ]
        style = dashboard.VersionStyle(["6.2.1"])
        system = [("2026-11-01T10:00:00", [("kernel", "5.14", "6.4")])]
        svg, unit = dashboard.svg_run_chart("Time", "s", points, style, {}, system)
        self.assertEqual(unit, "s")
        self.assertEqual(svg.count('class="sys"'), 1)
        self.assertIn("System changed before run 2", svg)
        self.assertIn("kernel 5.14 → 6.4", svg)


class VersionStyles(unittest.TestCase):
    def test_newest_is_darkest_and_shapes_cycle(self):
        style = dashboard.VersionStyle(["6.0.1", "6.2.1", "5.13.3", "6.1.0"])
        self.assertEqual(style.step("6.2.1"), dashboard.VERSION_STEPS)
        self.assertEqual(style.step("5.13.3"), dashboard.VERSION_STEPS - 3)
        self.assertEqual(style.shape("5.13.3"), "circle")
        self.assertEqual(style.shape("6.0.1"), "square")
        many = dashboard.VersionStyle(["1.{0}.0".format(i) for i in range(10)])
        self.assertEqual(many.step("1.0.0"), 1)  # older than the ramp: lightest


class UpgradeTable(unittest.TestCase):
    def test_cells_compare_like_for_like_and_colour_only_real_changes(self):
        def rows(old_times, new_times):
            out = []
            for i, s in enumerate(old_times):
                out.append(
                    (
                        "2026-10-0{0}T10:00:00".format(i + 1),
                        record("o", "k", "6.0.1", s),
                    )
                )
            for i, s in enumerate(new_times):
                out.append(
                    (
                        "2026-11-0{0}T10:00:00".format(i + 1),
                        record("n", "k", "6.2.1", s),
                    )
                )
            return out

        histories = {
            ("m1", "ParaView"): {
                "ex02_pvAnimation": rows([60.0, 60.5, 59.8], [40.0, 40.3, 39.9]),
                "ex03_pvIsosurfaceAnimation": rows(
                    [17.0, 17.4, 16.8], [17.2, 16.9, 17.3]
                ),
                "ex04_pvStreamlineAnimation": rows([70.0], [80.0]),
            }
        }
        states = {("m1", "ParaView"): {"retired": None}}
        cells = {
            c["vignette"]: c
            for c in dashboard.upgrade_cells(
                histories, states, "ParaView", "6.0.1", "6.2.1"
            )
        }
        self.assertEqual(cells["ex02_pvAnimation"]["cls"], "fast2")
        self.assertEqual(cells["ex03_pvIsosurfaceAnimation"]["cls"], "noise")
        self.assertEqual(cells["ex04_pvStreamlineAnimation"]["cls"], "one")
        self.assertAlmostEqual(cells["ex02_pvAnimation"]["change"], 40.0 / 60.0 - 1)


class Boundaries(unittest.TestCase):
    def cells(self, old_times, new_times):
        rows = [
            ("2026-10-0{0}T10:00:00".format(i + 1), record("o", "k", "6.0.1", t))
            for i, t in enumerate(old_times)
        ] + [
            ("2026-11-0{0}T10:00:00".format(i + 1), record("n", "k", "6.2.1", t))
            for i, t in enumerate(new_times)
        ]
        histories = {("m1", "ParaView"): {"ex02_pvAnimation": rows}}
        states = {("m1", "ParaView"): {"retired": None}}
        return dashboard.upgrade_cells(histories, states, "ParaView", "6.0.1", "6.2.1")[
            0
        ]

    def test_exactly_ten_percent_counts(self):
        cell = self.cells([100.0, 100.2, 99.8], [90.0, 90.1, 89.9])
        self.assertEqual(cell["cls"], "fast1")

    def test_median_and_mean_must_agree(self):
        # The median got faster (10 -> 8) but the mean got slower.
        cell = self.cells([10.0, 10.1, 9.9, 10.0, 10.05], [8.0, 8.0, 8.1, 30.0, 30.0])
        self.assertLess(cell["change"], -0.1)
        self.assertEqual(cell["cls"], "noise")
        self.assertIn(
            "mean moved the other way", dashboard.cell_tip(cell, "6.0.1", "6.2.1")
        )

    def test_small_significant_change_says_threshold(self):
        cell = self.cells([100.0, 100.1, 99.9], [95.0, 95.1, 94.9])
        self.assertEqual(cell["cls"], "noise")
        self.assertIn(
            "below the 10% threshold", dashboard.cell_tip(cell, "6.0.1", "6.2.1")
        )


class RunNumbers(unittest.TestCase):
    def test_a_run_keeps_its_number_when_a_metric_is_missing(self):
        runs = ["2026-10-01T10:00:00", "2026-10-02T10:00:00", "2026-10-03T10:00:00"]
        points = [(runs[1], "6.2.1", 5.0, ""), (runs[2], "6.2.1", 6.0, "")]
        style = dashboard.VersionStyle(["6.2.1"])
        system = [("2026-10-02T09:00:00", [("kernel", "a", "b")])]
        svg, _ = dashboard.svg_run_chart(
            "Memory", "MB", points, style, {}, system, runs
        )
        self.assertIn("Run 2 |", svg)
        self.assertIn("Run 3 |", svg)
        self.assertIn("System changed before run 2", svg)


class FastestRuns(unittest.TestCase):
    """dashboard.fastest_runs: the vignette page's bars and the index dots."""

    def test_median_of_the_latest_runs_repeats_and_one_revision(self):
        pin = dashboard.CURRENT_PINS["ParaView"]

        def rec(run, seconds, rev):
            r = record(run, "6.4", version=pin, seconds=seconds)
            r["_rev"] = rev
            return r

        histories = {
            ("a", "ParaView"): {
                "ex01_x": [
                    ("2026-11-20T01:00:00", rec("old", 99.0, 2)),
                    ("2026-11-23T01:00:00", rec("new", 10.0, 3)),
                    ("2026-11-23T01:01:00", rec("new", 30.0, 3)),
                    ("2026-11-23T01:02:00", rec("new", 11.0, 3)),
                ]
            },
            # Only an older revision of the code: not set beside "a".
            ("b", "ParaView"): {"ex01_x": [("2026-11-23T02:00:00", rec("x", 5.0, 2))]},
        }
        runs = dashboard.fastest_runs("ParaView", "ex01_x", histories, ["a", "b"])
        self.assertEqual([(c, t) for c, t, _ in runs], [("a", 11.0)])

    def test_the_bars_start_at_zero_and_sort_fastest_first(self):
        svg = dashboard.svg_latest_bars(
            [("b", 20.0, "2026-11-23T01:00:00"), ("a", 10.0, "2026-11-23T01:00:00")]
        )
        self.assertLess(svg.index(">a<"), svg.index(">b<"))
        self.assertIn(">0<", svg)


try:
    import matplotlib  # noqa: F401 - plot_metrics needs it

    HAVE_MATPLOTLIB = True
except ImportError:  # pragma: no cover - the harness CI installs it
    HAVE_MATPLOTLIB = False


@unittest.skipUnless(HAVE_MATPLOTLIB, "plot_metrics needs matplotlib")
class PlotMetricsRules(unittest.TestCase):
    """plot_metrics.py compares only runs of the newest vignette code."""

    def test_older_code_is_not_comparable_for_any_metric(self):
        import plot_metrics

        record = {"legacy": False, "old_code": True}
        self.assertTrue(plot_metrics._not_comparable(record, "execution_time"))
        record["old_code"] = False
        self.assertFalse(plot_metrics._not_comparable(record, "execution_time"))


if __name__ == "__main__":
    unittest.main()

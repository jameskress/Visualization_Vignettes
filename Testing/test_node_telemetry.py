#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_node_telemetry.py -- the schema-8 node telemetry and platform fields
#
#   python3 -m unittest -v Testing/test_node_telemetry.py
#
# Fake /proc, /sys and pm_counters trees, so it runs on any runner.
#
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import node_telemetry  # noqa: E402


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)
    os.chmod(path, mode)


class FakeProc(object):
    def __init__(self, root):
        self.root = root

    def add(self, pid, hwm_kb, step=None):
        base = os.path.join(self.root, str(pid))
        env = "PATH=/bin\0" + ("VV_SLURM_STEP_NAME=%s\0" % step if step else "")
        write(os.path.join(base, "environ"), env)
        write(
            os.path.join(base, "status"),
            "Name:\tx\nVmHWM:\t%d kB\nVmRSS:\t1 kB\n" % hwm_kb,
        )


class StepHighWaterMark(unittest.TestCase):
    def test_only_the_steps_processes_are_summed(self):
        with tempfile.TemporaryDirectory() as root:
            proc = FakeProc(root)
            proc.add(10, 1000, "vv-a")
            proc.add(11, 2000, "vv-a")
            proc.add(12, 4000, "vv-b")
            proc.add(13, 8000)
            write(os.path.join(root, "self", "status"), "")
            found = node_telemetry.step_hwm_kb("vv-a", proc=root)
            self.assertEqual(found, {10: 1000, 11: 2000})

    def test_a_name_that_is_a_prefix_does_not_match(self):
        with tempfile.TemporaryDirectory() as root:
            FakeProc(root).add(10, 1000, "vv-abc")
            self.assertEqual(node_telemetry.step_hwm_kb("vv-ab", proc=root), {})

    def test_the_cache_forgets_exited_processes(self):
        with tempfile.TemporaryDirectory() as root:
            proc = FakeProc(root)
            proc.add(10, 1000, "vv-a")
            cache = {}
            node_telemetry.step_hwm_kb("vv-a", proc=root, cache=cache)
            self.assertIn(10, cache)
            os.rename(os.path.join(root, "10"), os.path.join(root, "x10"))
            node_telemetry.step_hwm_kb("vv-a", proc=root, cache=cache)
            self.assertNotIn(10, cache)


class PowerAndGpu(unittest.TestCase):
    def test_pm_power_reads_values_and_the_hotter_cpu(self):
        with tempfile.TemporaryDirectory() as pm:
            write(os.path.join(pm, "power"), "612 W 1700000000 us\n")
            write(os.path.join(pm, "cpu_power"), "410 W 1700000000 us\n")
            write(os.path.join(pm, "cpu0_temp"), "51 C 1700000000 us\n")
            write(os.path.join(pm, "cpu1_temp"), "57 C 1700000000 us\n")
            self.assertEqual(
                node_telemetry.read_pm_power(pm),
                {"node_w": 612.0, "cpu_w": 410.0, "temp_c": 57.0},
            )

    def test_no_pm_counters_is_none(self):
        self.assertIsNone(node_telemetry.read_pm_power("/nonexistent/pm"))

    def test_nvidia_line_with_an_unsupported_field(self):
        self.assertEqual(
            node_telemetry.parse_nvidia_line("0, 2732, 12, [N/A]"),
            (0, 2732.0, 12.0, None),
        )
        self.assertIsNone(node_telemetry.parse_nvidia_line("No devices were found"))

    def test_power_figures_from_a_sampled_run(self):
        with tempfile.TemporaryDirectory() as pm:
            write(os.path.join(pm, "power"), "500 W 1 us\n")
            telemetry = node_telemetry.NodeTelemetry(power=True, gpu=False, pm_dir=pm)
            telemetry.POWER_PERIOD_S = 0.05
            telemetry.start()
            time.sleep(0.2)
            figures = telemetry.stop().figures()
            self.assertEqual(figures["power_peak_node_w"], 500.0)
            self.assertEqual(figures["power_mean_node_w"], 500.0)
            self.assertGreaterEqual(figures["power_samples"], 2)
            self.assertNotIn("gpu_telemetry", figures)
            self.assertNotIn("step_hwm_bytes", figures)

    def test_nothing_sampled_records_nothing(self):
        telemetry = node_telemetry.NodeTelemetry(power=False, gpu=False)
        self.assertEqual(telemetry.start().stop().figures(), {})


class Platform(unittest.TestCase):
    def test_platform_fields_from_a_fake_root(self):
        with tempfile.TemporaryDirectory() as root:
            cpu = os.path.join(root, "sys", "devices", "system", "cpu")
            write(
                os.path.join(cpu, "cpu0", "cpufreq", "scaling_driver"), "acpi-cpufreq\n"
            )
            write(os.path.join(cpu, "cpu0", "cpufreq", "cpuinfo_max_freq"), "3710000\n")
            write(os.path.join(cpu, "cpufreq", "boost"), "1\n")
            write(os.path.join(cpu, "smt", "active"), "0\n")
            for n in range(8):
                os.makedirs(
                    os.path.join(root, "sys", "devices", "system", "node", "node%d" % n)
                )
            write(
                os.path.join(
                    root, "sys", "kernel", "mm", "transparent_hugepage", "enabled"
                ),
                "always [madvise] never\n",
            )
            write(
                os.path.join(
                    root,
                    "sys",
                    "kernel",
                    "mm",
                    "hugepages",
                    "hugepages-2048kB",
                    "nr_hugepages",
                ),
                "0\n",
            )
            write(
                os.path.join(root, "proc", "cpuinfo"),
                "processor\t: 0\nmicrocode\t: 0xa101148\n",
            )
            write(
                os.path.join(root, "proc", "cmdline"),
                "root=nfs:secret-host:/img quiet\n",
            )
            out = node_telemetry.host_platform(root)
            self.assertEqual(out["cpu_driver"], "acpi-cpufreq")
            self.assertEqual(out["cpu_max_mhz"], 3710)
            self.assertTrue(out["cpu_boost"])
            self.assertFalse(out["smt_active"])
            self.assertEqual(out["numa_nodes"], 8)
            self.assertEqual(out["thp"], "madvise")
            self.assertEqual(out["hugepages_2m"], 0)
            self.assertEqual(out["cpu_microcode"], "0xa101148")
            # The command line names a host: only a digest is kept.
            self.assertEqual(len(out["kernel_cmdline_digest"]), 12)
            self.assertNotIn("secret-host", repr(out))

    def test_missing_files_are_left_out(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(node_telemetry.host_platform(root), {})


class DashboardSystemSettings(unittest.TestCase):
    def test_schema8_settings_are_system_changes(self):
        """The platform fields node_telemetry records reach the dashboard's
        system-change markers; a setting seen for the first time is not a
        change."""
        import dashboard

        def rec(run, kernel, boost=None):
            info = {"release": kernel}
            if boost is not None:
                info["cpu_boost"] = boost
            return {"run_id": run, "machine_info": info}

        rows = {
            "ex00": [
                ("2026-01-01T00:00:00", rec("a", "5.14")),
                ("2026-02-01T00:00:00", rec("b", "5.14", True)),
                ("2026-03-01T00:00:00", rec("c", "6.4", False)),
                ("2026-04-01T00:00:00", rec("d", "6.4", False)),
            ]
        }
        self.assertEqual(
            dashboard.platform_changes(rows),
            [
                (
                    "2026-03-01T00:00:00",
                    [("kernel", "5.14", "6.4"), ("boost", "True", "False")],
                )
            ],
        )

if __name__ == "__main__":
    unittest.main()

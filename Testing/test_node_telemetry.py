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

    def add(self, pid, hwm_kb, step=None, slurm_step=None):
        base = os.path.join(self.root, str(pid))
        env = "PATH=/bin\0" + ("VV_SLURM_STEP_NAME=%s\0" % step if step else "")
        if slurm_step is not None:
            env += "SLURM_STEP_ID=%s\0" % slurm_step
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


class SequentialSteps(unittest.TestCase):
    """CodeRabbit on #140: VisIt's engines run one after another."""

    def test_groups_come_from_the_slurm_step(self):
        with tempfile.TemporaryDirectory() as root:
            proc = FakeProc(root)
            proc.add(10, 300, "vv-a", slurm_step="4294967291")  # the harness
            proc.add(11, 1000, "vv-a", slurm_step="72")  # engine 1, rank 0
            proc.add(12, 1000, "vv-a", slurm_step="72")  # engine 1, rank 1
            proc.add(13, 1500, "vv-a", slurm_step="73")  # engine 2
            groups = {}
            found = node_telemetry.step_hwm_kb("vv-a", proc=root, groups=groups)
            self.assertEqual(len(found), 4)
            self.assertEqual(groups[11], "72")
            # The harness's own step is the tool tree, not a step's ranks.
            sums = node_telemetry.step_sums(found, groups, "4294967291")
            self.assertEqual(sums, {"72": 2000, "73": 1500})

    def test_figures_are_per_step_and_the_tree_is_separate(self):
        telemetry = node_telemetry.NodeTelemetry(step_name="vv-a", gpu=False)
        telemetry._memory_samples = 1
        # pid 11 reused in step 73 is a different process from pid 11 in 72.
        telemetry._hwm = {
            (10, "b"): 300,
            (11, "72"): 1000,
            (12, "72"): 1000,
            (11, "73"): 1500,
        }
        telemetry._step_pss_peak = {"72": 1400, "73": 1200}
        telemetry._tree_pss_peak = 1650
        telemetry._pss_samples = 3
        telemetry._own_step = "b"
        out = telemetry.figures()
        # The engines never ran together: the larger step, never their sum,
        # and the harness's own processes are not in the step figures.
        self.assertEqual(out["step_hwm_bytes"], 2000 * 1024)
        self.assertEqual(out["step_pss_peak_bytes"], 1400 * 1024)
        self.assertEqual(out["tool_tree_pss_peak_bytes"], 1650 * 1024)
        self.assertEqual(out["step_hwm_steps"], 2)
        self.assertEqual(out["step_hwm_processes"], 4)

    def test_pss_is_read_from_smaps_rollup(self):
        with tempfile.TemporaryDirectory() as root:
            write(
                os.path.join(root, "7", "smaps_rollup"),
                "00400000-ff [rollup]\nRss:  900 kB\nPss:  640 kB\n",
            )
            self.assertEqual(node_telemetry.pss_kb(7, proc=root), 640)
            self.assertIsNone(node_telemetry.pss_kb(8, proc=root))

    def test_the_pss_poll_paces_itself_on_large_processes(self):
        from unittest import mock

        telemetry = node_telemetry.NodeTelemetry(step_name="vv-a", gpu=False)
        calls = []

        def slow_pss(pid, proc="/proc"):
            calls.append(pid)
            time.sleep(0.05)  # a large process: 50 ms per read
            return 1000

        with mock.patch.object(
            node_telemetry, "step_hwm_kb", side_effect=lambda *a, **k: {1: 500}
        ), mock.patch.object(node_telemetry, "pss_kb", side_effect=slow_pss):
            telemetry.start()
            time.sleep(1.2)
            telemetry.stop()
        # At most 10% of a core: about one 50 ms read per 0.5 s, not ten a
        # second, while the cheap VmHWM poll keeps its 0.1 s period.
        self.assertLessEqual(len(calls), 4)
        self.assertGreaterEqual(telemetry._memory_samples, 6)


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
                    [("kernel", "5.14", "6.4"), ("boost", "on", "off")],
                )
            ],
        )


class NvidiaSmiLifetime(unittest.TestCase):
    def test_an_immediate_stop_still_ends_nvidia_smi(self):
        """stop() right after start() must not leave nvidia-smi polling."""
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "nvidia-smi")
            with open(fake, "w") as fh:
                fh.write(
                    "#!/bin/sh\nwhile true; do echo '0, 10, 5, 50'; sleep 0.05; done\n"
                )
            os.chmod(fake, 0o755)
            with mock.patch.object(node_telemetry.shutil, "which", return_value=fake):
                telemetry = node_telemetry.NodeTelemetry(gpu=True)
                telemetry.start().stop()
            self.assertIsNotNone(telemetry._smi)
            self.assertIsNotNone(telemetry._smi.poll(), "nvidia-smi still running")
            telemetry.figures()  # no error after an instant stop


class ExactPeakAsMemory(unittest.TestCase):
    """metrics.prefer_exact_peak: which runs take their memory from the ranks' PSS."""

    MB = 1024 * 1024

    def run_result(self, **changes):
        result = {
            "ranks_outside_tree": True,
            "job_nodes": 1,
            "step_pss_peak_bytes": 541 * self.MB,
            "step_hwm_bytes": 600 * self.MB,
            "succeeded": True,
            "returncode": 0,
            "slurm_steps": [
                {
                    "step": "1.79",
                    "total_mem_bytes": 231 * self.MB,
                    "max_task_mem_bytes": 231 * self.MB,
                    "cpu_seconds": 3.0,
                }
            ],
            "local_tree": {"peak_pss_bytes": 0, "tree_cpu_seconds": 0.1},
        }
        result.update(changes)
        return result

    def gather(self, run_result):
        import metrics

        return metrics.gather_metrics("ex01_pvScreenshot", 0.0, 2.0, run_result)

    def test_single_node_srun_takes_the_exact_peak(self):
        import metrics

        record = self.gather(self.run_result())
        self.assertEqual(record["memory_usage_mb"], 541.0)
        self.assertEqual(record["memory_measurement_scope"], metrics.STEP_PSS_SCOPE)
        self.assertEqual(record["slurm_memory_mb"], 231.0)
        self.assertEqual(record["slurm_memory_scope"], metrics.SLURM_SCOPE)
        # The ranks alone, the processes the new figure covers.
        self.assertEqual(record["slurm_step_memory_mb"], 231.0)
        self.assertEqual(record["step_hwm_mb"], 600.0)  # the upper bound

    def test_an_unsampled_step_still_gets_the_exact_peak(self):
        import metrics

        steps = [{"step": "1.0", "total_mem_bytes": 0, "cpu_seconds": 1.0}]
        record = self.gather(self.run_result(slurm_steps=steps))
        self.assertEqual(record["memory_usage_mb"], 541.0)
        self.assertEqual(record["memory_measurement_scope"], metrics.STEP_PSS_SCOPE)
        self.assertNotIn("slurm_memory_mb", record)
        self.assertNotIn("slurm_step_memory_mb", record)
        record = self.gather(self.run_result(slurm_steps=[]))
        self.assertEqual(record["memory_usage_mb"], 541.0)

    def test_other_runs_keep_their_figure(self):
        import metrics

        for changes in (
            {"job_nodes": 2},  # ranks on nodes the poller cannot read
            {"job_nodes": None},  # not under Slurm
            {"step_pss_peak_bytes": None},  # nothing sampled
        ):
            record = self.gather(self.run_result(**changes))
            self.assertEqual(record["memory_usage_mb"], 231.0, changes)
            self.assertEqual(
                record["memory_measurement_scope"], metrics.SLURM_SCOPE, changes
            )
            self.assertNotIn("slurm_memory_mb", record)
        # A local tree keeps PSS, which counts shared pages once.
        local = {
            "peak_pss_mb": 300.0,
            "step_pss_peak_bytes": 541 * self.MB,
            "job_nodes": 1,
        }
        record = self.gather(local)
        self.assertEqual(record["memory_usage_mb"], 300.0)
        self.assertEqual(record["memory_measurement_scope"], metrics.PSS_SCOPE)

    def test_the_slurm_figure_has_its_own_scope(self):
        import drift

        self.assertEqual(drift.scope_of("slurm_memory_mb"), "slurm_memory_scope")
        self.assertEqual(drift.scope_of("step_hwm_mb"), None)


if __name__ == "__main__":
    unittest.main()

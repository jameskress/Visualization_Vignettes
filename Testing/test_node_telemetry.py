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

    def test_a_partial_poll_does_not_count(self):
        from unittest import mock

        telemetry = node_telemetry.NodeTelemetry(step_name="vv-a", gpu=False)
        telemetry._own_step = "b"

        def scan(*a, groups=None, **k):
            groups.update({1: "72", 2: "72"})
            return {1: 500, 2: 500}

        import itertools

        # Poll 1: rank 2 unreadable. Poll 2: both read. Later polls: unreadable.
        reads = itertools.chain([400, None, 300, 350], itertools.repeat(None))

        with mock.patch.object(
            node_telemetry, "step_hwm_kb", side_effect=scan
        ), mock.patch.object(
            node_telemetry, "pss_kb", side_effect=lambda pid, proc="/proc": next(reads)
        ):
            telemetry.start()
            time.sleep(0.35)
            telemetry.stop()
        # Only the complete poll (300 + 350) counts, not the partial 400.
        self.assertEqual(telemetry._step_pss_peak, {"72": 650})

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

    def test_a_new_step_is_polled_at_once_despite_the_pacing(self):
        """A short step that starts between two paced polls of a large run
        still gets its PSS sample, so the run keeps the exact figure."""
        from unittest import mock

        telemetry = node_telemetry.NodeTelemetry(step_name="vv-a", gpu=False)
        telemetry._own_step = "own"
        scans = []

        def scan(*args, **kwargs):
            # By scan number, not by clock: the second step is there for
            # scans 3 and 4 only, well inside the 2 s the pacing then waits.
            scans.append(1)
            groups = kwargs["groups"]
            found = {1: 500}
            groups[1] = "0"
            if len(scans) in (3, 4):
                found[2] = 400
                groups[2] = "1"
            return found

        def slow_pss(pid, proc="/proc"):
            time.sleep(0.2)  # 0.2 s per read: the pacing waits 2 s
            return 1000

        with mock.patch.object(
            node_telemetry, "step_hwm_kb", side_effect=scan
        ), mock.patch.object(node_telemetry, "pss_kb", side_effect=slow_pss):
            telemetry.start()
            deadline = time.time() + 10
            while len(scans) < 6 and time.time() < deadline:
                time.sleep(0.05)
            telemetry.stop()
        figures = telemetry.figures()
        self.assertEqual(figures["step_hwm_steps"], 2)
        self.assertEqual(figures["step_pss_steps"], 2)


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

    def test_gpu_energy_integrates_power_over_the_run(self):
        e = node_telemetry.gpu_energy_j
        # Trapezoids between samples: 100 W then 200 W over 1 s is 150 J.
        self.assertAlmostEqual(e([(0.0, 100.0), (1.0, 200.0)]), 150.0)
        # The ends hold the nearest sample: 0.5 s before the first at 100 W,
        # 0.5 s after the last at 200 W.
        self.assertAlmostEqual(e([(1.0, 100.0), (2.0, 200.0)], 0.5, 2.5), 300.0)
        # One sample in a run shorter than the sampling period still counts
        # the whole run.
        self.assertAlmostEqual(e([(0.2, 60.0)], 0.0, 0.7), 42.0)
        # A missing power reading ([N/A]) is skipped; none at all is None.
        self.assertAlmostEqual(e([(0.0, 10.0), (1.0, None), (2.0, 10.0)]), 20.0)
        # A sample timed after the run ended does not stretch the run: 0 to
        # 1 s at 50 W is 50 J, whatever arrives at 1.2 s.
        self.assertAlmostEqual(e([(0.2, 50.0), (1.2, 50.0)], 0.0, 1.0), 50.0)
        self.assertIsNone(e([(0.0, None)]))
        self.assertIsNone(e([]))

    def test_gpu_energy_from_a_sampled_run(self):
        """A fake nvidia-smi at a steady 50 W: energy is 50 W times the run's
        length, per GPU, and gpu_energy_joules sums the GPUs."""
        from unittest import mock

        import metrics

        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "nvidia-smi")
            with open(fake, "w") as fh:
                fh.write(
                    "#!/bin/sh\nwhile true; do echo '0, 10, 5, 50'; "
                    "echo '1, 0, 0, 25'; sleep 0.1; done\n"
                )
            os.chmod(fake, 0o755)
            with mock.patch.object(node_telemetry.shutil, "which", return_value=fake):
                telemetry = node_telemetry.NodeTelemetry(gpu=True).start()
                time.sleep(1.0)
                figures = telemetry.stop().figures()
        length = telemetry._ended - telemetry._began
        gpus = {g["index"]: g for g in figures["gpu_telemetry"]}
        self.assertAlmostEqual(gpus[0]["energy_j"], 50 * length, delta=0.2)
        self.assertAlmostEqual(gpus[1]["energy_j"], 25 * length, delta=0.2)
        fields = metrics.node_telemetry_fields(figures)
        self.assertAlmostEqual(fields["gpu_energy_joules"], 75 * length, delta=0.4)

    def test_gpu_energy_total_needs_every_gpu(self):
        import metrics

        one = {"gpu_telemetry": [{"index": 0, "energy_j": 10.0}, {"index": 1}]}
        self.assertNotIn("gpu_energy_joules", metrics.node_telemetry_fields(one))

    def test_a_second_stop_keeps_the_first_end(self):
        telemetry = node_telemetry.NodeTelemetry(gpu=False).start()
        telemetry.stop()
        ended = telemetry._ended
        time.sleep(0.05)
        telemetry.stop()
        self.assertEqual(telemetry._ended, ended)

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

    def test_a_node_like_one_seen_before_is_not_a_change(self):
        """A shared pool's nodes differ: alternating between two kinds of
        node marks the second kind once, then nothing (ibex-cpu's microcode
        and kernel command line vary by node)."""
        import dashboard

        def rec(run, microcode):
            return {"run_id": run, "machine_info": {"cpu_microcode": microcode}}

        rows = {
            "ex00": [
                ("2026-01-01T00:00:00", rec("a", "0xb002162")),
                ("2026-01-02T00:00:00", rec("b", "0x830104d")),
                ("2026-01-03T00:00:00", rec("c", "0xb002162")),
                ("2026-01-04T00:00:00", rec("d", "0x830104d")),
            ]
        }
        self.assertEqual(
            dashboard.platform_changes(rows),
            [
                (
                    "2026-01-02T00:00:00",
                    [("CPU microcode", "0xb002162", "0x830104d")],
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

    def test_stop_does_not_wait_for_nvidia_smi_to_exit(self):
        """stop() kills nvidia-smi rather than asking it to exit: the real one
        takes about 0.56 s to act on SIGTERM, and that time landed on every
        vignette of a GPU machine. This fake ignores SIGTERM altogether."""
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "nvidia-smi")
            with open(fake, "w") as fh:
                fh.write(
                    "#!/bin/sh\ntrap '' TERM\n"
                    "while true; do echo '0, 10, 5, 50'; sleep 0.05; done\n"
                )
            os.chmod(fake, 0o755)
            with mock.patch.object(node_telemetry.shutil, "which", return_value=fake):
                telemetry = node_telemetry.NodeTelemetry(gpu=True).start()
                time.sleep(0.2)
                began = time.time()
                telemetry.stop()
                took = time.time() - began
            self.assertLess(took, 1.0)
            self.assertIsNotNone(telemetry._smi.poll(), "nvidia-smi still running")


class ExactPeakAsMemory(unittest.TestCase):
    """metrics.prefer_exact_peak: which runs take their memory from the ranks' PSS."""

    MB = 1024 * 1024

    def run_result(self, **changes):
        result = {
            "ranks_outside_tree": True,
            "job_nodes": 1,
            "step_pss_peak_bytes": 541 * self.MB,
            "step_pss_steps": 1,
            "step_hwm_steps": 1,
            "srun_steps_expected": 1,
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

    def test_a_step_without_a_pss_sample_keeps_slurms_figure(self):
        import metrics

        # Two engine steps seen, only one with a complete PSS sample.
        record = self.gather(self.run_result(step_pss_steps=1, step_hwm_steps=2))
        self.assertEqual(record["memory_measurement_scope"], metrics.SLURM_SCOPE)
        self.assertEqual(record["memory_usage_mb"], 231.0)

    def test_a_step_neither_scan_saw_keeps_slurms_figure(self):
        import metrics

        # The vignette started two engine steps; one began and ended between
        # two scans, so both counts say one.
        record = self.gather(
            self.run_result(step_pss_steps=1, step_hwm_steps=1, srun_steps_expected=2)
        )
        self.assertEqual(record["memory_measurement_scope"], metrics.SLURM_SCOPE)
        # The number of steps started unknown (no results JSON): Slurm's.
        record = self.gather(self.run_result(srun_steps_expected=None))
        self.assertEqual(record["memory_measurement_scope"], metrics.SLURM_SCOPE)
        # Every step the vignette started was sampled: the exact figure.
        record = self.gather(
            self.run_result(step_pss_steps=2, step_hwm_steps=2, srun_steps_expected=2)
        )
        self.assertEqual(record["memory_measurement_scope"], metrics.STEP_PSS_SCOPE)

    def test_the_slurm_figure_has_its_own_scope(self):
        import drift

        self.assertEqual(drift.scope_of("slurm_memory_mb"), "slurm_memory_scope")
        self.assertEqual(drift.scope_of("step_hwm_mb"), None)


if __name__ == "__main__":
    unittest.main()


class PmEnergyGuard(unittest.TestCase):
    """run_tests.pm_energy: readings that cannot be right are not recorded."""

    def reading(self, node, cpu, memory):
        return {
            "node_joules": node,
            "cpu_joules": cpu,
            "memory_joules": memory,
            "generation": 7,
        }

    def test_a_normal_reading(self):
        import run_tests

        used = run_tests.pm_energy(self.reading(0, 0, 0), self.reading(600, 300, 170))
        self.assertEqual(
            used, {"node_joules": 600, "cpu_joules": 300, "memory_joules": 170}
        )

    def test_unchanged_counters_are_no_reading(self):
        import run_tests

        self.assertIsNone(
            run_tests.pm_energy(self.reading(5, 5, 5), self.reading(5, 5, 5))
        )

    def test_a_part_larger_than_the_node_drops_the_split(self):
        import metrics
        import run_tests

        # Shaheen, 24 Nov: CPU 206003 J against 5935 J for the node.
        used = run_tests.pm_energy(
            self.reading(0, 0, 0), self.reading(5935, 206003, 1785)
        )
        self.assertEqual(used["node_joules"], 5935)
        self.assertIsNone(used["cpu_joules"])
        self.assertIsNone(used["memory_joules"])
        fields = metrics.node_telemetry_fields(
            {"ranks_outside_tree": True, "pm_energy": used}
        )
        self.assertEqual(fields["energy_pm_node_joules"], 5935.0)
        self.assertNotIn("energy_cpu_joules", fields)

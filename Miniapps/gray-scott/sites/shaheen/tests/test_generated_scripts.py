#!/usr/bin/env python3
"""Tests for the Shaheen experiment generator (generate_experiments.py).

Each test pins down a failure the November 2026 Paper 2 sweep hit on Shaheen
III, so it cannot come back unnoticed (sites/shaheen/README.md has the
measurements). The generator runs once, into a temporary directory, with stub
binaries and the sweep's own flags (--telemetry --repeats 3; --catalyst-stage
needs a real build and is left out). No Slurm is needed: sbatch and squeue
are stubbed where a script calls them.

    python -m unittest -v Miniapps/gray-scott/sites/shaheen/tests/test_generated_scripts.py
"""
import contextlib
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SHAHEEN = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(SHAHEEN, "..", "..", "..", ".."))
GENERATOR = os.path.join(SHAHEEN, "2026-WOIV-scripts", "generate_experiments.py")
AUDIT_DIR = os.path.join(SHAHEEN, "large-runs")

# Runs whose output is recorded and deleted by their reduction (DATA_CLEANUP):
# every data run and every baseline. Renders keep their images, and the
# initialisations keep the checkpoints every other run restarts from.
CLEANED = re.compile(r"_(data|baseline)(_r\d\d)?$")


def write_stub(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, 0o755)


class GeneratedScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vv-gen-test-")
        bin_dir = os.path.join(cls.tmp, "bin")
        os.makedirs(bin_dir)
        for b in ("gray-scott", "analysis-reader"):
            write_stub(os.path.join(bin_dir, b), "exit 0")
        cls.runs = os.path.join(cls.tmp, "runs")
        cls.scripts = os.path.join(cls.tmp, "scripts")
        r = subprocess.run(
            [
                sys.executable,
                GENERATOR,
                "--repo-path",
                REPO,
                "--bin-path",
                bin_dir,
                "--results-dir",
                cls.runs,
                "--output-dir",
                cls.scripts,
                "--telemetry",
                "--repeats",
                "3",
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"generator failed:\n{r.stdout}\n{r.stderr}")
        cls.jobs = sorted(glob.glob(os.path.join(cls.scripts, "*.sbat")))
        cls.ids = [os.path.basename(j)[:-5] for j in cls.jobs]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def read(self, path):
        with open(path) as f:
            return f.read()

    def reduce_path(self, run_id):
        return os.path.join(self.runs, run_id, "reduce.sbat")

    # --- shape -------------------------------------------------------------

    def test_generates_the_sweep(self):
        self.assertGreater(len(self.jobs), 700)
        self.assertTrue(any(i.startswith("init_") for i in self.ids))
        self.assertFalse(
            any("kombyne" in i for i in self.ids),
            "Kombyne jobs on Shaheen need --with-kombyne (#165)",
        )

    def test_every_script_parses(self):
        scripts = self.jobs + [self.reduce_path(i) for i in self.ids]
        bad = []
        for s in scripts:
            if os.path.exists(s):
                r = subprocess.run(["bash", "-n", s], capture_output=True, text=True)
                if r.returncode != 0:
                    bad.append(f"{s}: {r.stderr.strip()}")
        self.assertEqual(bad, [])

    # --- the run job -------------------------------------------------------

    def test_reduction_is_submitted_before_the_run(self):
        # A job killed by a node failure, the time limit or a cancel used to
        # submit no reduction, so its output stayed on disk (3 TB, 24 Nov 2026).
        for job in self.jobs:
            s = self.read(job)
            owner = s.find("> $OUTPUT_DIR/run_job.txt")
            early = s.find("--dependency=afterany:$SLURM_JOB_ID")
            start = s.find('echo "PHASE run_start')
            with self.subTest(job=os.path.basename(job)):
                self.assertNotEqual(owner, -1, "run_job.txt not written")
                self.assertNotEqual(early, -1, "no afterany reduction")
                self.assertLess(owner, early, "owner marker must precede the reduction")
                self.assertLess(early, start, "reduction must be queued before the run")
                self.assertIn("REDUCE_SUBMIT_FAILED", s, "end-of-job fallback missing")
                self.assertIn(
                    "#SBATCH --no-requeue",
                    s,
                    "a requeued run would lose its output to its queued reduction",
                )

    # --- the reduction -----------------------------------------------------

    def test_cleanup_covers_data_runs_and_baselines_only(self):
        for i in self.ids:
            path = self.reduce_path(i)
            if not os.path.exists(path):
                continue
            with self.subTest(run=i):
                has = "DATA_RECORD=" in self.read(path)
                self.assertEqual(has, bool(CLEANED.search(i)))

    def test_ascent_cleanup_includes_its_run_directory_output(self):
        # Ascent writes ascent_data.cycle_* beside data/, which the cleanup
        # missed until #162 (about 5 TB of the sweep).
        ascent = [i for i in self.ids if re.search(r"_ascent_data(_r\d\d)?$", i)]
        self.assertTrue(ascent)
        for i in ascent:
            with self.subTest(run=i):
                self.assertIn("ascent_data.cycle_*", self.read(self.reduce_path(i)))

    def test_ownership_is_checked_before_anything_is_deleted(self):
        # A reduction held for a killed job must not delete a later run's
        # output (CodeRabbit on #167).
        for i in self.ids:
            path = self.reduce_path(i)
            if not os.path.exists(path):
                continue
            s = self.read(path)
            lock = s.find("mkdir $LOCK")
            owner = s.find("OWNER_RUN=$(cat $OUTPUT_DIR/run_job.txt")
            with self.subTest(run=i):
                self.assertNotEqual(lock, -1)
                self.assertNotEqual(owner, -1)
                self.assertLess(lock, owner)
                # Every deletion or archive comes after the check; removing
                # this reduction's own lock (the EXIT trap) is the exception.
                for marker in ("DATA_RECORD=", "rm -", "tar -czf", "mv "):
                    for m in re.finditer(re.escape(marker), s):
                        line = s[
                            s.rfind("\n", 0, m.start()) + 1 : s.find("\n", m.start())
                        ]
                        if line.lstrip().startswith("#") or "$LOCK" in line:
                            continue
                        self.assertLess(
                            owner,
                            m.start(),
                            f"{line.strip()!r} before the ownership check",
                        )

    # --- settings ----------------------------------------------------------

    def test_only_paper1_inline_data_runs_overwrite(self):
        # Overwriting made the Catalyst write 63% slower per step (64+4 A/B,
        # 24 Nov 2026); Paper 2 inline and in transit must match (#163).
        for i in self.ids:
            path = os.path.join(self.runs, i, "settings.json")
            if not os.path.exists(path):
                continue
            with open(path) as f:
                ow = json.load(f).get("overwrite_last_step")
            expect = (
                i.startswith("paper1_")
                and "_inline_" in i
                and bool(re.search(r"_data$", i))
            )
            with self.subTest(run=i):
                self.assertEqual(bool(ow), expect)

    # --- behaviour, with stubs ---------------------------------------------

    def data_run(self):
        return next(
            i for i in self.ids if re.search(r"^paper2_strong_.*_adios_data_r01$", i)
        )

    def run_reduce(self, run_id, run_job_id):
        env = dict(os.environ, RUN_JOB_ID=str(run_job_id), SLURM_JOB_ID="999")
        return subprocess.run(
            ["bash", self.reduce_path(run_id)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_reduction_for_another_job_keeps_the_output(self):
        i = self.data_run()
        d = os.path.join(self.runs, i)
        os.makedirs(os.path.join(d, "data"), exist_ok=True)
        open(os.path.join(d, "data", "step.bp"), "w").close()
        record = os.path.join(self.runs, f"{i}_data_output.json")
        try:
            with open(os.path.join(d, "run_job.txt"), "w") as f:
                f.write("200\n")
            r = self.run_reduce(i, 100)
            self.assertIn("does nothing", r.stdout)
            self.assertTrue(os.path.exists(os.path.join(d, "data", "step.bp")))
            self.assertFalse(os.path.exists(record))
            # The owning job's reduction records, then deletes.
            with open(os.path.join(d, "run_job.txt"), "w") as f:
                f.write("100\n")
            self.run_reduce(i, 100)
            self.assertFalse(os.path.exists(os.path.join(d, "data")))
            with open(record) as f:
                self.assertIn('"job": "100"', f.read())
        finally:
            for p in (record, os.path.join(d, "run_job.txt")):
                if os.path.exists(p):
                    os.remove(p)
            shutil.rmtree(os.path.join(d, "reduce.lock"), ignore_errors=True)

    def lock_wait_loop(self):
        s = self.read(os.path.join(self.scripts, self.data_run() + ".sbat"))
        start = s.index('echo "$SLURM_JOB_ID" > $OUTPUT_DIR/run_job.txt')
        end = s.index("\ndone\n", start) + len("\ndone\n")
        return s[start:end].replace("sleep 30", "sleep 0").replace("sleep 5", "sleep 0")

    def run_loop(self, live_polls):
        t = tempfile.mkdtemp(dir=self.tmp)
        out = os.path.join(t, "out")
        os.makedirs(os.path.join(out, "reduce.lock"))
        with open(os.path.join(out, "reduce.lock", "job"), "w") as f:
            f.write("12345\n")
        bin_dir = os.path.join(t, "bin")
        os.makedirs(bin_dir)
        count = os.path.join(t, "n")
        # squeue lists the lock's job for the first live_polls calls.
        write_stub(
            os.path.join(bin_dir, "squeue"),
            f"n=$(cat {count} 2>/dev/null || echo 0); n=$((n+1)); echo $n > {count}\n"
            f"[ $n -le {live_polls} ] && echo 12345; exit 0",
        )
        loop = os.path.join(t, "loop.sh")
        with open(loop, "w") as f:
            f.write(self.lock_wait_loop())
        env = dict(
            os.environ,
            OUTPUT_DIR=out,
            SLURM_JOB_ID="777",
            PATH=bin_dir + os.pathsep + os.environ["PATH"],
        )
        r = subprocess.run(
            ["bash", loop], env=env, capture_output=True, text=True, timeout=60
        )
        with open(os.path.join(out, "run_job.txt")) as f:
            return r, f.read().strip()

    def test_run_waits_for_a_running_reduction(self):
        r, owner = self.run_loop(live_polls=2)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(owner, "777")
        self.assertEqual(r.stdout.count("Waiting for reduction job 12345"), 2)

    def test_run_ignores_a_stale_lock(self):
        r, owner = self.run_loop(live_polls=0)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("Waiting", r.stdout)


class AuditRuns(unittest.TestCase):
    def test_killed_run_with_partial_csvs_is_not_a_success(self):
        # A killed job prints no "Run exit status", but its reduction (held
        # until the job ends) still writes partial CSVs.
        sys.path.insert(0, AUDIT_DIR)
        try:
            import audit_runs
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as t:
            for run_id, status in (
                ("paper2_weak_N0008_adios_data_r01", None),
                ("paper2_weak_N0008_adios_data_r02", 0),
            ):
                d = os.path.join(t, run_id)
                os.makedirs(d)
                with open(os.path.join(d, "slurm-1.out"), "w") as f:
                    f.write("PHASE run_start 1\n")
                    if status is not None:
                        f.write(f"Run exit status: {status}\n")
                open(os.path.join(t, f"{run_id}_writer.csv"), "w").close()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                audit_runs.audit_runs(t)
            self.assertIn("SUMMARY: 1 Successful", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

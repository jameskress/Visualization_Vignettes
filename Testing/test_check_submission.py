#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_check_submission.py -- the checks a pull request of results must pass
#
#   python3 -m unittest -v Testing/test_check_submission.py
#
# Author: James Kress, <james@jameskress.com>

import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_submission as cs  # noqa: E402

VIGNETTE = os.path.join("ParaView_Vignettes", "ex01_pvScreenshot", "Testing")
NOW = datetime.datetime(2026, 11, 22, 12, 0, 0)


def record(**changes):
    rec = {
        "test_name": "ex01_pvScreenshot",
        "metrics_schema": 7,
        "run_id": "mycluster-cpu-2026-11-22",
        "execution_time": 3.2,
        "run_succeeded": True,
        "machine_info": {"node": "cn01"},
    }
    rec.update(changes)
    return rec


def git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        os.makedirs(os.path.join(self.repo, VIGNETTE, "Baseline"))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, config, document, raw=None):
        path = os.path.join(VIGNETTE, "performance_metrics_{0}.json".format(config))
        with open(os.path.join(self.repo, path), "w", encoding="utf-8") as fh:
            fh.write(raw if raw is not None else json.dumps(document, indent=4))
        return path

    def problems(self, path, base=None):
        return cs.check_file(self.repo, path, base, now=NOW)

    def test_a_good_file_passes(self):
        path = self.write("mycluster-cpu", {"2026-11-22T10:00:00.5": record()})
        self.assertEqual(self.problems(path), [])

    def test_structure(self):
        path = self.write("mycluster-cpu", None, raw="{not json")
        self.assertIn("does not parse", self.problems(path)[0])
        path = self.write("mycluster-cpu", [record()])
        self.assertIn("not a JSON object", self.problems(path)[0])
        path = self.write(
            "mycluster-cpu",
            {
                "yesterday": record(),
                "2026-11-22T10:00:00": record(test_name="ex02_pvAnimation"),
                "2026-11-22T11:00:00": "a string",
            },
        )
        found = " | ".join(self.problems(path))
        self.assertIn("[yesterday]: key is not an ISO-8601 timestamp", found)
        self.assertIn("test_name 'ex02_pvAnimation'", found)
        self.assertIn("record is not an object", found)

    def test_configuration_names(self):
        self.assertIsNone(cs.name_problem("mycluster-egl-a100"))
        self.assertIn("letters, digits", cs.name_problem("my cluster"))
        self.assertIn("looks like a host name", cs.name_problem("node7.example.org"))
        # A host already given a public name in dashboard.PUBLIC_NAMES.
        self.assertIsNone(cs.name_problem("KW61316.kaust.edu.sa"))
        path = self.write("login1.example.org", {"2026-11-22T10:00:00": record()})
        self.assertIn("looks like a host name", self.problems(path)[0])

    def test_new_records_only_against_base(self):
        old = {"2026-01-01T00:00:00": record(metrics_schema=None, run_id=None)}
        path = self.write("mycluster-cpu", old)
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        new = dict(old)
        new["2026-11-22T10:00:00"] = record(
            metrics_schema=4, run_id="", execution_time="3", run_succeeded=None
        )
        self.write("mycluster-cpu", new)
        found = self.problems(path, base="HEAD")
        # The old record is not judged by today's rules; the new one is.
        self.assertFalse(any("2026-01-01" in p for p in found), found)
        joined = " | ".join(found)
        for text in (
            "metrics_schema 4",
            "no run_id",
            "execution_time is not a number",
            "run_succeeded is not true or false",
        ):
            self.assertIn(text, joined)
        # Without a base only the structure is checked.
        self.assertEqual(self.problems(path), [])

    def test_a_file_new_to_the_base_is_all_new(self):
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-qm", "empty", "--allow-empty")
        path = self.write("mycluster-cpu", {"2026-11-22T10:00:00": record(run_id=None)})
        self.assertIn("no run_id", self.problems(path, base="HEAD")[0])

    def test_host_name_fallback_and_future(self):
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-qm", "empty", "--allow-empty")
        path = self.write(
            "cn01",
            {
                "2026-11-22T10:00:00": record(),
                "2027-01-01T00:00:00": record(),
            },
        )
        joined = " | ".join(self.problems(path, base="HEAD"))
        self.assertIn("the configuration is the host name 'cn01'", joined)
        self.assertIn("[2027-01-01T00:00:00]: timestamp is in the future", joined)

    def test_baseline_directory_names(self):
        site = os.path.join(self.repo, VIGNETTE, "Baseline", "node7.example.org")
        os.makedirs(site)
        self.assertEqual(cs.baseline_problems(self.repo), [])  # no image yet
        open(os.path.join(site, "ex01.png"), "w").close()
        self.assertIn("looks like a host name", cs.baseline_problems(self.repo)[0])

    def test_main_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.write("mycluster-cpu", {"2026-11-22T10:00:00": record()})
            self.assertEqual(cs.main(["--repo", self.repo]), 0)
            self.write("bad name", {"2026-11-22T10:00:00": record()})
            self.assertEqual(cs.main(["--repo", self.repo]), 1)
        self.assertIn("configuration name 'bad name'", out.getvalue())


class RealRepository(unittest.TestCase):
    def test_the_committed_records_pass(self):
        repo = cs.REPO_ROOT
        problems = []
        for path in cs.history_files(repo):
            problems.extend(cs.check_file(repo, path))
        problems.extend(cs.baseline_problems(repo))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

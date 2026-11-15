#
# Visualization Vignettes
#
# test_io_sampler.py -- the process-tree I/O sum, with the reap order fixed
#
# The real-process checks in LOCAL_VALIDATION 4b.16 cannot choose when the
# kernel reaps a child, so they cannot show that a child reaped between its
# parent's read and its own is counted once. These drive
# run_tests._PeakRssSampler with fake processes whose readings and exits are
# scripted, so each order is exercised exactly:
#
#   python3 -m unittest Testing/test_io_sampler.py
#
# Standard library only; psutil is needed only for its exception classes.
#
# Author: James Kress, <james@jameskress.com>
#
import collections
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psutil  # noqa: E402  pyright: ignore[reportMissingModuleSource]

import run_tests  # noqa: E402

IO = collections.namedtuple("IO", "read_bytes write_bytes read_chars write_chars")
Mem = collections.namedtuple("Mem", "rss")
Full = collections.namedtuple("Full", "pss")
Times = collections.namedtuple("Times", "user system")
Uids = collections.namedtuple("Uids", "real effective saved")

MB = 1 << 20


class FakeProcess(object):
    """A process whose I/O reading, exit and children are scripted."""

    def __init__(self, pid, write_mb, children=(), io_error=None, status="sleeping"):
        self.pid = pid
        self.write = write_mb * MB
        self._children = list(children)
        self.io_error = io_error
        self._status = status
        self.uid = os.getuid()

    def memory_info(self):
        return Mem(10 * MB)

    def memory_full_info(self):
        return Full(5 * MB)

    def cpu_times(self):
        return Times(1.0, 0.1)

    def create_time(self):
        return 1000.0 + self.pid

    def num_threads(self):
        return 1

    def io_counters(self):
        if self.io_error is not None:
            raise self.io_error
        return IO(0, self.write, 0, self.write)

    def children(self, recursive=False):
        # Parents before children, as psutil lists them.
        out = []
        for child in self._children:
            out.append(child)
            out.extend(child.children(recursive=True))
        return out

    def uids(self):
        return Uids(self.uid, self.uid, self.uid)

    def status(self):
        if self._status == "gone":
            raise psutil.NoSuchProcess(self.pid)
        return self._status


def sample(*roots):
    """Run one sample per root (successive states of one tree)."""
    sampler = run_tests._PeakRssSampler(roots[0].pid)
    for root in roots:
        sampler._sample_once(root)
    io = sampler.io_totals
    return None if io is None else io[1] / MB


class TreeIoSum(unittest.TestCase):
    def test_child_reaped_before_parent_read_counts_once(self):
        # The child was reaped before the parent's read (150 MB, the child's
        # 50 included); the walk had listed the child, whose read now fails.
        child = FakeProcess(2, 50, io_error=psutil.NoSuchProcess(2))
        root = FakeProcess(1, 150, [child])
        self.assertEqual(sample(root), 150)

    def test_child_read_before_its_reap_counts_once(self):
        # The parent was read before the reap (100 MB, child excluded) and
        # the child afterwards, still alive (50 MB).
        root = FakeProcess(1, 100, [FakeProcess(2, 50)])
        self.assertEqual(sample(root), 150)

    def test_parent_read_before_reap_child_gone_by_its_read(self):
        # The one order a sample misses: the parent excludes the child and
        # the child has gone by its own read. That sample is low; the next,
        # with the child reaped into the root, has it, and the maximum wins.
        first = FakeProcess(
            1, 100, [FakeProcess(2, 50, io_error=psutil.NoSuchProcess(2))]
        )
        second = FakeProcess(1, 150)
        self.assertEqual(sample(first, second), 150)

    def test_grandchild_reaped_through_a_reaped_parent(self):
        # Root -> mid -> leaf; leaf reaped by mid, mid by root, both gone by
        # their reads: the root holds all of it.
        leaf = FakeProcess(3, 50, io_error=psutil.NoSuchProcess(3))
        mid = FakeProcess(2, 50, [leaf], io_error=psutil.NoSuchProcess(2))
        root = FakeProcess(1, 70, [mid])
        self.assertEqual(sample(root), 70)

    def test_zombie_of_this_user_is_skipped(self):
        child = FakeProcess(2, 50, io_error=psutil.AccessDenied(2), status="zombie")
        root = FakeProcess(1, 100, [child])
        self.assertEqual(sample(root), 100)

    def test_live_non_dumpable_process_withholds_the_total(self):
        # PR_SET_DUMPABLE 0: refuses /proc/<pid>/io and stays alive.
        child = FakeProcess(2, 50, io_error=psutil.AccessDenied(2), status="sleeping")
        root = FakeProcess(1, 100, [child])
        self.assertIsNone(sample(root))

    def test_other_users_process_withholds_the_total(self):
        child = FakeProcess(2, 50, io_error=psutil.AccessDenied(2), status="zombie")
        child.uid = os.getuid() + 1
        root = FakeProcess(1, 100, [child])
        self.assertIsNone(sample(root))

    def test_platform_without_io_counters_withholds_the_total(self):
        root = FakeProcess(1, 100, io_error=AttributeError("io_counters"))
        self.assertIsNone(sample(root))


NON_DUMPABLE_CHILD = """
import ctypes, sys, time
if ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
    sys.exit(3)
print("ready", flush=True)
time.sleep(30)
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "PR_SET_DUMPABLE is Linux")
class RealNonDumpableChild(unittest.TestCase):
    def test_live_non_dumpable_child_withholds_the_total(self):
        # A real process of this user that made itself non-dumpable refuses
        # /proc/<pid>/io and stays alive: the total must be None, not low.
        parent = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import subprocess, sys; "
                "subprocess.run([sys.executable, '-c', sys.argv[1]])",
                NON_DUMPABLE_CHILD,
            ],
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        try:
            self.assertEqual(parent.stdout.readline().strip(), "ready")
            sampler = run_tests._PeakRssSampler(parent.pid)
            sampler._sample_once(psutil.Process(parent.pid))
            self.assertIsNone(sampler.io_totals)
        finally:
            for child in psutil.Process(parent.pid).children(recursive=True):
                child.kill()
            parent.kill()
            parent.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()

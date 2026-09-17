#!/usr/bin/env python3
#
# Visualization Vignettes -- In Situ Vignettes
#
# is00_validate.py
#
# Independent verdict on is00_zeroCopyAdapter. It runs the binary and judges
# the result from BOTH the exit code and the emitted log, because trusting
# only one of them is how regressions get through.
#
# This is the pattern the ParaView/VisIt harness is missing today:
# Testing/test_suite.py computes image-comparison results, writes them to
# image_comparison_results.json, and then check_failure() reads only
# text_comparison_results.json -- so a rendering regression is recorded and
# never fails the build. Here, any FAIL line is a failure, full stop.
#
import argparse
import re
import shutil
import subprocess
import sys

CHECK_RE = re.compile(r"^\s*\[(PASS|FAIL|SKIP)\]\s+(.*?)\s*$")
SUMMARY_RE = re.compile(r"=== .* (ALL CHECKS PASSED|\d+ CHECK\(S\) FAILED) ===")

# Checks the vignette must actually report. A check that silently stops being
# emitted is treated as a failure, so deleting an assertion cannot make the
# suite greener.
REQUIRED = [
    "set_external aliases the simulation buffer",
    "writes through the sim buffer reach the node",
    "mesh passes blueprint::mesh::verify",
    "every rank contributed a non-empty field",
]


def run(binary, mpiexec, ranks, timeout):
    if ranks > 1:
        if not mpiexec or not shutil.which(mpiexec):
            print(f"error: mpiexec '{mpiexec}' not usable for a {ranks}-rank run")
            return None
        cmd = [mpiexec, "-n", str(ranks), binary]
    else:
        cmd = [binary]

    print(f"Executing: {' '.join(cmd)}")
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        print(f"error: vignette exceeded {timeout}s -- treating as a failure "
              "(a hung collective is a bug, not a skip)")
        return None


def main():
    p = argparse.ArgumentParser(description="Validate is00_zeroCopyAdapter output.")
    p.add_argument("--binary", required=True)
    p.add_argument("--mpiexec", default="mpiexec")
    p.add_argument("--ranks", type=int, default=1)
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()

    proc = run(args.binary, args.mpiexec, args.ranks, args.timeout)
    if proc is None:
        return 1

    log = proc.stdout + proc.stderr
    print(log)

    failures = []

    # 1. Exit code.
    if proc.returncode != 0:
        failures.append(f"non-zero exit code {proc.returncode}")

    # 2. No FAIL lines.
    seen = {}
    for line in log.splitlines():
        m = CHECK_RE.match(line)
        if m:
            status, name = m.group(1), m.group(2)
            # Strip any trailing detail the C++ side appended.
            key = next((r for r in REQUIRED if name.startswith(r)), name)
            seen[key] = status
            if status == "FAIL":
                failures.append(f"check reported FAIL: {name}")

    # 3. Every required check actually ran.
    for required in REQUIRED:
        if required not in seen:
            failures.append(f"required check never reported: {required}")

    # 4. The run reached its own summary line (i.e. did not die mid-way).
    if not SUMMARY_RE.search(log):
        failures.append("vignette did not print a summary line")

    print("-" * 68)
    if failures:
        print("is00_zeroCopyAdapter.validate: FAILED")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"is00_zeroCopyAdapter.validate: PASSED ({len(seen)} checks reported)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

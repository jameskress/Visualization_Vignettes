#!/usr/bin/env python3
"""Syntax-check every `run:` block in the workflows, as the runner sees it.

WHY THIS EXISTS

A job body used to be a payload inside `docker run ... bash -c '...'`. One
apostrophe in one comment closed that single quote early, the double quotes
after it went live in the outer shell, and both CI jobs died with

    line 74: unexpected EOF while looking for matching `"'

before running anything. Checking the extracted payload could not catch it,
because the payload was fine; the embedding was broken. The runner writes
each `run:` block to a file and runs bash against it, so that is what this
checks.

    python3 .github/scripts/check_workflow_shell.py

Exits non-zero and prints the offending block on any syntax error.
"""
import glob
import os
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("PyYAML not installed; skipping (pip install pyyaml to enable)")
    sys.exit(0)

# GitHub expands ${{ ... }} before bash ever sees it. Substitute something
# shell-safe so the check tests the quoting rather than the templating.
PLACEHOLDER = "EXPR"


def expand(text):
    out = []
    rest = text
    while "${{" in rest:
        head, _, tail = rest.partition("${{")
        _, _, tail = tail.partition("}}")
        out.append(head)
        out.append(PLACEHOLDER)
        rest = tail
    out.append(rest)
    return "".join(out)


def main():
    failures = 0
    checked = 0
    for path in sorted(glob.glob(".github/workflows/*.yml")):
        document = yaml.safe_load(open(path, encoding="utf-8"))
        for job_name, job in (document.get("jobs") or {}).items():
            for index, step in enumerate(job.get("steps") or []):
                script = step.get("run")
                if not script:
                    continue
                checked += 1
                handle, temp = tempfile.mkstemp(suffix=".sh")
                with os.fdopen(handle, "w") as out:
                    out.write(expand(script))
                result = subprocess.run(["bash", "-n", temp], stderr=subprocess.PIPE)
                os.unlink(temp)
                if result.returncode != 0:
                    failures += 1
                    label = step.get("name", "step %d" % index)
                    print("FAIL %s / %s / %s" % (path, job_name, label))
                    print(result.stderr.decode("utf-8", "replace").rstrip())
                    print("-" * 60)
    print("%d run block(s) checked, %d with syntax errors" % (checked, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

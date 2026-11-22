#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_docs_pins.py -- the recipes name the builds the suite actually pins
#
#   python3 -m unittest -v Testing/test_docs_pins.py
#
# The quick-start recipes in Testing/README.md went on loading ParaView 6.0.1
# and VisIt 3.4.1 for weeks after the suite moved to 6.2.1 and 3.5.0. This
# fails when a module name or a --paraview_version / --visit_version in that
# file, or the default the MODULES.sh scripts load, differs from
# CURRENT_PINS in dashboard.py. Older versions named in prose (history,
# measurements) are fine; only commands are checked. Move the pins and the
# recipes together (AGENTS.md: docs ship with the change).
#
# Standard library only, so it runs on a bare runner.
#
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dashboard  # noqa: E402

PINS = {
    "paraview": dashboard.CURRENT_PINS["ParaView"],
    "visit": dashboard.CURRENT_PINS["VisIt"],
}


def read(*parts):
    with open(os.path.join(ROOT, *parts), "r") as handle:
        return handle.read()


def commands(text):
    """Lines that are commands: inside fenced code blocks, or inline `code`."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            out.append(line)
        else:
            out.extend(re.findall(r"`([^`]+)`", line))
    return out


VERSION_IN_COMMAND = re.compile(
    r"\b(paraview|visit)/(\d+\.\d+\.\d+)"
    r"|--(paraview|visit)_version(?:\s+|=)[\"']?(\d+\.\d+\.\d+)"
)


def stale_lines(lines, pins=PINS):
    """The command lines that name a ParaView or VisIt build other than the pins."""
    stale = []
    for line in lines:
        for match in VERSION_IN_COMMAND.finditer(line):
            tool = match.group(1) or match.group(3)
            version = match.group(2) or match.group(4)
            if version != pins[tool]:
                stale.append(line.strip())
                break
    return stale


class RecipesMatchThePins(unittest.TestCase):
    def test_testing_readme_modules_and_version_flags(self):
        stale = stale_lines(commands(read("Testing", "README.md")))
        self.assertEqual(
            stale,
            [],
            "Testing/README.md recipes name builds other than CURRENT_PINS {0}".format(
                PINS
            ),
        )

    def test_add_your_site_guide(self):
        stale = stale_lines(commands(read("Testing", "ADD_YOUR_SITE.md")))
        self.assertEqual(
            stale,
            [],
            "Testing/ADD_YOUR_SITE.md recipes name builds other than "
            "CURRENT_PINS {0}".format(PINS),
        )

    def test_modules_scripts_load_the_pinned_builds_by_default(self):
        paraview = read("ParaView_Vignettes", "MODULES.sh")
        versions = set(re.findall(r"^\s*currentVersion=(\S+)", paraview, re.M))
        self.assertEqual(versions, {PINS["paraview"]})
        visit = read("VisIt_Vignettes", "MODULES.sh")
        loads = set(re.findall(r"^\s*module load visit/(\d+\.\d+\.\d+)", visit, re.M))
        loads |= set(re.findall(r"VV_VISIT_MODULE:-visit/(\d+\.\d+\.\d+)", visit))
        self.assertEqual(loads, {PINS["visit"]})

    def test_the_check_catches_a_stale_recipe(self):
        # The detector itself: stale lines are found, pinned and prose ones are not.
        sample = (
            "ParaView 6.0.1 was slower, see `module load paraview/6.0.1-mesa`.\n"
            "```bash\nmodule load visit/{0}\n--visit_version 3.4.1\n"
            "--paraview_version \"6.0.1\"\n--visit_version='3.4.2'\n```".format(
                PINS["visit"]
            )
        )
        self.assertEqual(
            stale_lines(commands(sample)),
            [
                "module load paraview/6.0.1-mesa",
                "--visit_version 3.4.1",
                '--paraview_version "6.0.1"',
                "--visit_version='3.4.2'",
            ],
        )


if __name__ == "__main__":
    unittest.main()

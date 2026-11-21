#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_dashboard_names.py -- no host name reaches the public dashboard
#
#   python3 -m unittest -v Testing/test_dashboard_names.py
#
# Standard library only, so it runs on a bare runner.
#
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402

HOST = "KW61316.kaust.edu.sa"


class PublicNames(unittest.TestCase):
    def test_a_host_named_configuration_is_published_under_its_public_name(self):
        self.assertEqual(dashboard.public_name(HOST), "workstation")
        self.assertEqual(dashboard.public_name("ibex-cpu"), "ibex-cpu")

    def test_an_unlisted_dotted_name_stops_the_build(self):
        with self.assertRaises(SystemExit):
            dashboard.public_name("node01.example.org")

    def test_short_host_is_replaced_only_as_a_whole_token(self):
        self.assertEqual(
            dashboard.public_text("KW61316-backfill-2026"), "workstation-backfill-2026"
        )
        self.assertEqual(dashboard.public_text("kw61316-x"), "workstation-x")
        self.assertEqual(dashboard.public_text("kw613160-x"), "kw613160-x")

    def test_every_string_of_a_record_is_scrubbed(self):
        record = {
            "run_id": "KW61316-2026-11-15",
            "baseline": {"image_sources": {HOST: 3, "shared": 2}},
            "notes": ["engine_hosts=" + HOST],
            "execution_time": 3.5,
        }
        histories = {(HOST, "ParaView"): {"ex00_pvQuery": [("t1", record)]}}
        out = dashboard.publish_names(histories)
        self.assertEqual(list(out), [("workstation", "ParaView")])
        published = out[("workstation", "ParaView")]["ex00_pvQuery"][0][1]
        self.assertNotIn("KW61316", repr(published).upper())
        self.assertEqual(published["execution_time"], 3.5)
        self.assertEqual(published["baseline"]["image_sources"]["workstation"], 3)

    def test_two_configurations_with_one_public_name_stop_the_build(self):
        histories = {
            (HOST, "ParaView"): {},
            ("workstation", "ParaView"): {},
        }
        with self.assertRaises(SystemExit):
            dashboard.publish_names(histories)


if __name__ == "__main__":
    unittest.main()

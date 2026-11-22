#!/usr/bin/env python3
#
# Visualization Vignettes
#
# test_site_pages.py -- the landing page and gallery generator
#
#   python3 -m unittest -v Testing/test_site_pages.py
#
# Author: James Kress, <james@jameskress.com>

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_pages  # noqa: E402

# The smallest valid PNG: one white pixel.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea7d6a4ea0000000049454e44ae426082"
)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def make_repo(root):
    """Two suites; ex01 has images and a per-site set, ex00 only numbers."""
    for suite, name, images in (
        ("ParaView_Vignettes", "ex00_pvQuery", []),
        ("ParaView_Vignettes", "ex01_pvScreenshot", ["ex01.png"]),
        ("VisIt_Vignettes", "ex01_visitScreenshot", ["b_0001.png", "a_0000.png"]),
        ("VisIt_Vignettes", "ex99_visitNew", ["new.jpg"]),
    ):
        base = os.path.join(root, suite, name, "Testing", "Baseline")
        os.makedirs(base)
        open(os.path.join(base, "known_good_value.txt"), "w").close()
        for image in images:
            with open(os.path.join(base, image), "wb") as fh:
                fh.write(PNG)
    site = os.path.join(
        root, "VisIt_Vignettes", "ex01_visitScreenshot", "Testing", "Baseline", "site-a"
    )
    os.makedirs(site)
    with open(os.path.join(site, "a_0000.png"), "wb") as fh:
        fh.write(PNG)
    # A subdirectory with no image is not a site set.
    os.makedirs(os.path.join(os.path.dirname(site), "notes"))
    # Not a vignette directory.
    os.makedirs(os.path.join(root, "VisIt_Vignettes", "data", "Testing", "Baseline"))


class Baselines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        make_repo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_set_only_sorted(self):
        found = site_pages.baselines(self.repo)
        self.assertEqual(sorted(found), [0, 1, 99])
        visit = found[1]["images"]["VisIt"]
        self.assertEqual(
            [os.path.basename(p) for p in visit], ["a_0000.png", "b_0001.png"]
        )
        self.assertEqual(found[1]["sites"], {"ParaView": 0, "VisIt": 1})
        self.assertEqual(found[0]["images"]["ParaView"], [])
        self.assertNotIn("VisIt", found[0]["dir"])

    def test_build_without_pillow(self):
        out = os.path.join(self.repo, "_site")
        with mock.patch.object(site_pages, "_preview", return_value=None):
            vignettes, images = site_pages.build(out, self.repo)
        self.assertEqual((vignettes, images), (3, 4))
        gallery = read(os.path.join(out, "gallery", "index.html"))
        # Without previews the gallery shows the full images, unsized.
        self.assertIn(
            "src='img/VisIt_Vignettes/ex01_visitScreenshot/Testing/Baseline/"
            "a_0000.png' loading='lazy'",
            gallery,
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    out,
                    "gallery",
                    "img",
                    "ParaView_Vignettes",
                    "ex01_pvScreenshot",
                    "Testing",
                    "Baseline",
                    "ex01.png",
                )
            )
        )
        self.assertIn("No image: this vignette checks numbers.", gallery)
        self.assertIn("(+1 site-specific set)", gallery)
        # The per-site image itself is not copied.
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    out,
                    "gallery",
                    "img",
                    "VisIt_Vignettes",
                    "ex01_visitScreenshot",
                    "Testing",
                    "Baseline",
                    "site-a",
                )
            )
        )
        # A vignette without a description falls back to its directory name.
        self.assertIn("ex99 ex99_visitNew", gallery)
        landing = read(os.path.join(out, "root", "index.html"))
        self.assertIn("href='dashboard/'", landing)
        self.assertIn("href='gallery/'", landing)

    def test_previews_are_sized(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed")
        out = os.path.join(self.repo, "_site")
        site_pages.build(out, self.repo)
        gallery = read(os.path.join(out, "gallery", "index.html"))
        self.assertIn("ex01.preview.jpg' width='1' height='1'", gallery)

    def test_rebuild_drops_old_images(self):
        out = os.path.join(self.repo, "_site")
        stale = os.path.join(out, "gallery", "img", "gone.png")
        os.makedirs(os.path.dirname(stale))
        open(stale, "w").close()
        with mock.patch.object(site_pages, "_preview", return_value=None):
            site_pages.build(out, self.repo)
        self.assertFalse(os.path.exists(stale))

    def test_output_is_escaped(self):
        found = {
            1: {"dir": {"VisIt": "ex01_<b>"}, "images": {"VisIt": []}, "sites": {}}
        }
        page = site_pages.render_gallery(found, {})
        self.assertNotIn("<b>", page)
        self.assertIn("ex01_&lt;b&gt;", page)


class RealRepository(unittest.TestCase):
    def test_every_vignette_number_is_described(self):
        """A new vignette needs its line in ABOUT, or it shows a bare name."""
        found = site_pages.baselines()
        missing = sorted(set(found) - set(site_pages.ABOUT))
        self.assertEqual(missing, [], "add these to site_pages.ABOUT")


if __name__ == "__main__":
    unittest.main()

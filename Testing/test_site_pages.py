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
        self.assertIn("ex99 ex99_visitNew</h3>", gallery)
        self.assertIn("ex99 ex99_visitNew</a>", gallery)
        landing = read(os.path.join(out, "root", "index.html"))
        self.assertIn("href='dashboard/'", landing)
        self.assertIn("href='gallery/'", landing)

    def test_gallery_order(self):
        """ParaView before VisIt, vignettes ex00 up, frames in natural order."""
        base = os.path.join(
            self.repo, "VisIt_Vignettes", "ex01_visitScreenshot", "Testing", "Baseline"
        )
        for name in ("f_10.png", "f_2.png"):
            with open(os.path.join(base, name), "wb") as fh:
                fh.write(PNG)
        out = os.path.join(self.repo, "_site")
        with mock.patch.object(site_pages, "_preview", return_value=None):
            site_pages.build(out, self.repo)
        gallery = read(os.path.join(out, "gallery", "index.html"))
        order = [
            gallery.index(marker)
            for marker in (
                "id='paraview-ex00'",
                "id='paraview-ex01'",
                "id='visit-ex01'",
                "id='visit-ex99'",
            )
        ]
        self.assertEqual(order, sorted(order))
        self.assertLess(gallery.index("f_2.png"), gallery.index("f_10.png"))
        # Each frame's caption names its vignette in the alt text.
        self.assertIn("alt='VisIt Screenshot baseline: f_2.png'", gallery)

    def test_previews_are_sized(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed")
        out = os.path.join(self.repo, "_site")
        site_pages.build(out, self.repo)
        gallery = read(os.path.join(out, "gallery", "index.html"))
        self.assertIn(
            "preview/ParaView_Vignettes/ex01_pvScreenshot/Testing/Baseline/ex01.png.jpg' width='1' height='1'",
            gallery,
        )

    def test_previews_never_collide(self):
        """No preview shares a path with another preview or with an image.

        frame.png and frame.jpg share a stem; a baseline literally named
        frame.png.preview.jpg used to be overwritten by frame.png's preview.
        """
        base = os.path.join(
            self.repo, "ParaView_Vignettes", "ex01_pvScreenshot", "Testing", "Baseline"
        )
        for name in ("ex01.jpg", "ex01.png.preview.jpg"):
            with open(os.path.join(base, name), "wb") as fh:
                fh.write(PNG)
        out = os.path.join(self.repo, "_site")
        written = []

        def preview(source, target):
            written.append(target)
            return (1, 1)

        with mock.patch.object(site_pages, "_preview", side_effect=preview):
            site_pages.build(out, self.repo)
        images = {
            os.path.join(d, f)
            for d, _, files in os.walk(os.path.join(out, "gallery", "img"))
            for f in files
        }
        self.assertEqual(len(written), len(set(written)))
        self.assertEqual(set(written) & images, set())
        names = sorted(os.path.basename(t) for t in written if "ex01." in t)
        self.assertEqual(
            names, ["ex01.jpg.jpg", "ex01.png.jpg", "ex01.png.preview.jpg.jpg"]
        )

    def test_paths_are_url_encoded(self):
        base = os.path.join(
            self.repo,
            "VisIt_Vignettes",
            "ex10_visitColormapFidelity",
            "Testing",
            "Baseline",
        )
        os.makedirs(base)
        with open(os.path.join(base, "frame#1 a.png"), "wb") as fh:
            fh.write(PNG)
        out = os.path.join(self.repo, "_site")
        with mock.patch.object(site_pages, "_preview", return_value=None):
            site_pages.build(out, self.repo)
        gallery = read(os.path.join(out, "gallery", "index.html"))
        self.assertIn("Baseline/frame%231%20a.png'", gallery)
        # Only the caption and alt text keep the name as it is.
        self.assertNotIn("Baseline/frame#1", gallery)
        # The landing page's strip uses ex10 VisIt, so it is encoded there too.
        landing = read(os.path.join(out, "root", "index.html"))
        self.assertIn("src='gallery/img/VisIt_Vignettes/", landing)
        self.assertIn("frame%231%20a.png'", landing)

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
        self.assertNotIn("ex01_<b>", page)
        self.assertIn("ex01_%3Cb%3E", page)

    def test_gallery_has_the_viewer_and_plain_links(self):
        """Each frame stays a plain link to its full-size file (works without
        JavaScript); the viewer dialog and its script come once, after main."""
        found = {
            5: {
                "dir": {"ParaView": "ex05_Time"},
                "images": {"ParaView": ["a/ex05_1.png", "a/ex05_2.png"]},
                "sites": {},
            }
        }
        placed = {
            "a/ex05_1.png": ("img/a/ex05_1.png", "preview/a/ex05_1.png.jpg", None),
            "a/ex05_2.png": ("img/a/ex05_2.png", "preview/a/ex05_2.png.jpg", None),
        }
        page = site_pages.render_gallery(found, placed)
        self.assertIn("<a href='img/a/ex05_2.png'>", page)
        self.assertEqual(page.count("id='viewer'"), 1)
        self.assertLess(page.index("</main>"), page.index("<dialog"))
        self.assertIn("ArrowRight", page)


class RealRepository(unittest.TestCase):
    def test_every_vignette_number_is_described(self):
        """A new vignette needs its line in ABOUT, or it shows a bare name."""
        found = site_pages.baselines()
        missing = sorted(set(found) - set(site_pages.ABOUT))
        self.assertEqual(missing, [], "add these to site_pages.ABOUT")


if __name__ == "__main__":
    unittest.main()

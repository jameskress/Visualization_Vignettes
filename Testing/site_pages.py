#!/usr/bin/env python3
#
# Visualization Vignettes
#
# site_pages.py -- the landing page and the image gallery for GitHub Pages
#
# Writes, beside the dashboard that Testing/dashboard.py builds:
#
#   <out>/root/index.html        the landing page: what the project is, and
#                                links to the dashboard, the gallery and
#                                the repository
#   <out>/gallery/index.html     every vignette's committed baseline images,
#                                ParaView and VisIt side by side
#   <out>/gallery/img/...        the images
#   <out>/gallery/preview/...    a small preview of each, apart from the
#                                images so no baseline name can collide
#
# The images are the baselines the regression suite compares against
# (<suite>/<vignette>/Testing/Baseline/), so the gallery shows what each
# vignette is expected to draw. Only the default baseline set is shown; a
# site whose renderer differs keeps its own set in a subdirectory, which the
# gallery counts but does not repeat.
#
# Previews are made with Pillow when it is installed (the Pages workflow
# installs it); without it the gallery links the full images, loaded lazily.
#
#   python3 Testing/site_pages.py --out _site
#
# Author: James Kress, <james@jameskress.com>

import argparse
import os
import re
import shutil
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard import REPO_ROOT, SUITES, VIGNETTE_RE, css, esc  # noqa: E402

REPO_URL = "https://github.com/jameskress/Visualization_Vignettes"
IMAGE = re.compile(r"\.(png|jpe?g)$", re.IGNORECASE)
PREVIEW_PX = 480

# What each vignette number shows, in words that fit both tools. A vignette
# not listed here still appears, under its directory name.
ABOUT = {
    0: ("Query", "Loads a dataset and checks its mesh statistics and metadata."),
    1: ("Screenshot", "The basic rendering pipeline, saved as an image."),
    2: ("Camera animation", "A camera path around the data, frame by frame."),
    3: ("Isosurface animation", "An isovalue swept through the field."),
    4: ("Streamlines", "Flow visualization with seeded streamlines."),
    5: ("Time series", "One rendering per time step of a multi-step file."),
    6: ("Large data", "A large dataset rendered in parallel."),
    7: (
        "Scaling",
        "Isosurface extraction across rank counts; geometry must not change.",
    ),
    8: ("Backend check", "Fails when a job that asked for a GPU renders in software."),
    9: ("Mesh topologies", "One contour pipeline over several mesh types."),
    10: (
        "Colormap fidelity",
        "One field through four transfer functions, each with a legend.",
    ),
    11: ("State verification", "A saved session reloaded headlessly and stepped."),
    12: ("Extract regression", "Image, data and numeric extracts side by side."),
}

SITE_CSS = """
.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px;
margin:16px 0 4px}
.hero img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:6px;display:block;
background:var(--na)}
.links{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;
margin:16px 0}
.links a.card{display:block;text-decoration:none;margin:0}
.links a.card:hover,.links a.card:focus-visible{border-color:var(--ink2)}
.links .card p{margin:4px 0 0;color:var(--ink2)}
.toc{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:13px;margin:8px 0}
.vig{scroll-margin-top:12px}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.pair h4{margin:6px 0 4px;font-size:13px;font-weight:600}
.frames{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:4px}
.frames.one{grid-template-columns:minmax(0,360px)}
.frames a{display:block}
.frames img{width:100%;height:auto;display:block;border-radius:4px;background:var(--na)}
.frames figure{margin:0}
.frames figcaption{font-size:11px;color:var(--muted);overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
"""


def page(title, body, footer):
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>{0}</title><style>{1}{2}</style></head><body><main>{3}"
        "<footer>{4}</footer></main></body></html>"
    ).format(esc(title), css(), SITE_CSS, body, footer)


def vignette_number(name):
    match = VIGNETTE_RE.match(name)
    return int(match.group(1)) if match else None


def baselines(repo=REPO_ROOT):
    """{number: {"dir": {tool: name}, "images": {tool: [path]}, "sites": {tool: n}}}

    Paths are relative to the repository. Images are the default set only;
    "sites" counts the per-site subdirectories that hold their own set.
    """
    found = {}
    for tool, suite in SUITES:
        root = os.path.join(repo, suite)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            number = vignette_number(name)
            base = os.path.join(root, name, "Testing", "Baseline")
            if number is None or not os.path.isdir(base):
                continue
            entry = found.setdefault(number, {"dir": {}, "images": {}, "sites": {}})
            entry["dir"][tool] = name
            entries = sorted(os.listdir(base))
            entry["images"][tool] = [
                os.path.join(suite, name, "Testing", "Baseline", f)
                for f in entries
                if IMAGE.search(f) and os.path.isfile(os.path.join(base, f))
            ]
            entry["sites"][tool] = sum(
                1
                for f in entries
                if os.path.isdir(os.path.join(base, f))
                and any(IMAGE.search(g) for g in os.listdir(os.path.join(base, f)))
            )
    return found


def _preview(source, target):
    """Write a small JPEG preview and return its (width, height).

    None when Pillow is missing or cannot read the image.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(source) as im:
            im.thumbnail((PREVIEW_PX, PREVIEW_PX))
            if im.mode not in ("RGB", "L"):
                flat = Image.new("RGB", im.size, (255, 255, 255))
                rgba = im.convert("RGBA")
                flat.paste(rgba, mask=rgba.getchannel("A"))
                im = flat
            im.save(target, "JPEG", quality=82, optimize=True)
            return im.size
    except (OSError, ValueError):
        return None


def copy_images(found, out, repo=REPO_ROOT):
    """Copy each image into <out>/img.

    Returns {repo path: (full, preview, size)}: both paths relative to <out>,
    and the preview's (width, height), or None when there is no preview.
    """
    placed = {}
    for entry in found.values():
        for paths in entry["images"].values():
            for path in paths:
                full = os.path.join("img", path.replace(os.sep, "/"))
                target = os.path.join(out, full)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(os.path.join(repo, path), target)
                # In its own tree, so no baseline (frame.png.preview.jpg, say)
                # can share a name with a preview, and with the whole source
                # name, extension too: foo.png and foo.jpg differ.
                preview = "preview/" + full[len("img/") :] + ".jpg"
                os.makedirs(os.path.dirname(os.path.join(out, preview)), exist_ok=True)
                size = _preview(target, os.path.join(out, preview))
                if size is None:
                    preview = full
                placed[path] = (full, preview, size)
    return placed


def url(path):
    """A relative path for href or src: percent-encoded ('frame#1.png' is not
    a fragment), separators kept, then HTML-escaped."""
    return esc(quote(path, safe="/"))


def _frames(paths, placed, tool, title):
    if not paths:
        return "<p class='note'>No image: this vignette checks numbers.</p>"
    figures = []
    for path in paths:
        full, preview, size = placed[path]
        name = os.path.basename(path)
        # The size reserves the image's space, so an #exNN link lands on
        # its section while the lazy images above it are still loading.
        dims = " width='{0}' height='{1}'".format(*size) if size else ""
        figures.append(
            "<figure><a href='{0}'><img src='{1}'{2} loading='lazy' "
            "decoding='async' alt='{3} {4} baseline: {5}'></a>"
            "<figcaption title='{5}'>{5}</figcaption></figure>".format(
                url(full), url(preview), dims, esc(tool), esc(title), esc(name)
            )
        )
    one = " one" if len(paths) == 1 else ""
    return "<div class='frames{0}'>{1}</div>".format(one, "".join(figures))


def describe(n, entry):
    """(title, sentence) for vignette n; an undescribed one goes by its name."""
    return ABOUT.get(n, (next(iter(entry["dir"].values())), ""))


def render_gallery(found, placed):
    numbers = sorted(found)
    toc = "".join(
        "<a href='#ex{0:02d}'>ex{0:02d} {1}</a>".format(
            n, esc(describe(n, found[n])[0])
        )
        for n in numbers
    )
    sections = []
    for n in numbers:
        entry = found[n]
        title, about = describe(n, entry)
        columns = []
        for tool, suite in SUITES:
            if tool not in entry["dir"]:
                continue
            name = entry["dir"][tool]
            sites = entry["sites"].get(tool, 0)
            extra = (
                " <span class='muted'>(+{0} site-specific set{1})</span>".format(
                    sites, "" if sites == 1 else "s"
                )
                if sites
                else ""
            )
            columns.append(
                "<div><h4><a href='{0}/tree/master/{1}/{2}'>{3}</a>{4}</h4>{5}</div>".format(
                    REPO_URL,
                    suite,
                    url(name),
                    esc(name),
                    extra,
                    _frames(entry["images"].get(tool, []), placed, tool, title),
                )
            )
        sections.append(
            "<section class='card vig' id='ex{0:02d}'><h3>ex{0:02d} {1}</h3>"
            "<p class='note'>{2}</p><div class='pair'>{3}</div></section>".format(
                n, esc(title), esc(about), "".join(columns)
            )
        )
    body = (
        "<p class='note'><a href='../'>Visualization Vignettes</a> &rsaquo; Gallery</p>"
        "<h1>Gallery</h1>"
        "<p class='lede'>What each vignette draws: the baseline images the "
        "regression suite compares every run against. Select an image for "
        "the full size.</p>"
        "<nav class='toc'>{0}</nav>{1}"
    ).format(toc, "".join(sections))
    footer = (
        "Built from the Testing/Baseline images in jameskress/Visualization_Vignettes "
        "by Testing/site_pages.py. Results of every run: "
        "<a href='../dashboard/'>dashboard</a>."
    )
    return page("Gallery - Visualization Vignettes", body, footer)


# A few baselines for the landing page's strip, chosen to show the range.
HERO = (
    (3, "ParaView"),
    (4, "ParaView"),
    (9, "ParaView"),
    (10, "VisIt"),
    (6, "VisIt"),
    (2, "VisIt"),
)


def hero_images(found, placed):
    picks = []
    for n, tool in HERO:
        paths = found.get(n, {}).get("images", {}).get(tool) or []
        if paths:
            title = ABOUT.get(n, ("", ""))[0]
            # The middle frame: a sequence's first frame is often sparse.
            middle = paths[len(paths) // 2]
            picks.append(
                "<a href='gallery/#ex{0:02d}'><img src='gallery/{1}' loading='lazy' "
                "alt='{2} ex{0:02d} {3}'></a>".format(
                    n, url(placed[middle][1]), esc(tool), esc(title)
                )
            )
    return "<div class='hero'>{0}</div>".format("".join(picks)) if picks else ""


def render_landing(found, placed):
    cards = (
        (
            "dashboard/",
            "Results dashboard",
            "The latest result of every vignette on every site and GPU "
            "configuration, and how time and memory moved across versions.",
        ),
        (
            "gallery/",
            "Gallery",
            "What each ParaView and VisIt vignette draws, from the images the "
            "regression suite checks against.",
        ),
        (
            REPO_URL,
            "Source and docs",
            "The vignettes, batch scripts for Ibex and Shaheen, the in situ "
            "examples and the test harness.",
        ),
    )
    links = "".join(
        "<a class='card' href='{0}'><h3>{1}</h3><p>{2}</p></a>".format(
            esc(href), esc(title), esc(text)
        )
        for href, title, text in cards
    )
    body = (
        "<h1>Visualization Vignettes</h1>"
        "<p class='lede'>A cookbook of examples, best practices and training "
        "material for scientific and in situ visualization: runnable ParaView "
        "and VisIt vignettes, often tailored for HPC systems. Each vignette is "
        "also a regression test, run on every site and tool version.</p>"
        "{0}<div class='links'>{1}</div>"
    ).format(hero_images(found, placed), links)
    footer = (
        "Built by Testing/site_pages.py from "
        "<a href='{0}'>jameskress/Visualization_Vignettes</a>.".format(REPO_URL)
    )
    return page("Visualization Vignettes", body, footer)


def build(out, repo=REPO_ROOT):
    found = baselines(repo)
    gallery = os.path.join(out, "gallery")
    root = os.path.join(out, "root")
    for directory in (gallery, root):
        shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory)
    placed = copy_images(found, gallery, repo)
    with open(os.path.join(gallery, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_gallery(found, placed))
    # The landing page links its strip into the gallery beside it.
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_landing(found, placed))
    return len(found), len(placed)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the landing page and gallery.")
    parser.add_argument("--out", default="_site", help="Output directory.")
    parser.add_argument("--repo", default=REPO_ROOT, help="Repository root.")
    args = parser.parse_args(argv)
    vignettes, images = build(args.out, args.repo)
    print(
        "wrote the landing page and a gallery of {0} images over {1} vignettes "
        "to {2}".format(images, vignettes, args.out)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
import datetime
import os
import re
import shutil
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402
from dashboard import (  # noqa: E402
    ABOUT,
    REPO_ROOT,
    REPO_URL,
    SUITES,
    VIGNETTE_RE,
    css,
    esc,
    site_header,
)

IMAGE = re.compile(r"\.(png|jpe?g)$", re.IGNORECASE)
PREVIEW_PX = 480
TOOLS = [tool for tool, _ in SUITES]


def natural_key(name):
    """frame_2 before frame_10: digit runs compare as numbers."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", name)
    ]


SITE_CSS = """
.toc{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13.5px;margin:8px 0 4px}
.toc b{font-weight:600;margin-right:4px}
.vig{scroll-margin-top:12px}
.frames{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.frames.one{grid-template-columns:minmax(0,420px)}
.frames a{display:block}
.frames img{width:100%;height:auto;display:block;border-radius:5px;background:var(--na)}
.frames figure{margin:0}
.frames figcaption{font-size:11.5px;color:var(--muted);overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.hero{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:32px;
align-items:start}
.hero .lede{font-size:1.1rem}
.who{font-size:14.5px;color:var(--ink2);max-width:62ch}
.who b{color:var(--ink);font-weight:600}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
.btn{display:inline-flex;align-items:center;font:600 15px/1 var(--sans);padding:12px 18px;
border-radius:8px;text-decoration:none;border:1px solid var(--accent)}
.btn.primary{background:var(--accent);color:var(--accent-ink)}
.btn.ghost{color:var(--accent)}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;
background:var(--ring);border:1px solid var(--ring);border-radius:10px;overflow:hidden}
.stat{background:var(--surface);padding:16px 18px}
.stat .v{font:500 1.9rem/1.1 var(--mono)}
.stat .k{font-size:13px;color:var(--ink2);margin-top:4px}
.stat.wide{grid-column:1/-1}
.strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.strip a{display:block;position:relative;border-radius:8px;overflow:hidden;
background:var(--na)}
.strip img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;
transition:transform .25s ease}
.strip a:hover img{transform:scale(1.03)}
.strip span{position:absolute;left:8px;bottom:8px;background:rgba(8,12,14,.75);color:#fff;
font:500 11.5px/1.2 var(--mono);padding:4px 7px;border-radius:5px}
.ctas{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.cta{display:flex;flex-direction:column;gap:8px;text-decoration:none;color:var(--ink);
min-width:0;margin:0}
a.cta:hover{border-color:var(--accent)}
.cta.span2{grid-column:span 2}
.cta.full{grid-column:1/-1}
.cta p{color:var(--ink2);font-size:14px;margin:0}
.cta .go{margin-top:auto;color:var(--accent);font-weight:600;font-size:14px}
.tag{font:500 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;
color:var(--accent)}
.cmd{display:flex;gap:8px;align-items:stretch}
.cmd code{flex:1;min-width:0;overflow-x:auto;white-space:nowrap;font:12px/1.5 var(--mono);
background:var(--na);padding:8px 10px;border-radius:6px}
.cmd button{font:600 12px var(--sans);border:1px solid var(--ring);background:var(--surface);
color:var(--ink);border-radius:6px;padding:0 10px;cursor:pointer}
.inside{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.inside ol{margin:0;padding:0;list-style:none;font-size:14px}
.inside li{display:grid;grid-template-columns:2.6em 1fr;gap:6px;padding:4px 0;
border-bottom:1px solid var(--grid)}
.inside li:last-child{border-bottom:0}
.inside .d{color:var(--muted);font-size:13px}
.kind{font:500 11px/1 var(--mono);color:var(--muted);letter-spacing:.06em;
text-transform:uppercase;margin:12px 0 6px}
@media (max-width:860px){.hero{grid-template-columns:minmax(0,1fr)}
.ctas,.inside{grid-template-columns:repeat(2,minmax(0,1fr))}
.strip{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.ctas,.inside{grid-template-columns:minmax(0,1fr)}
.cta.span2{grid-column:auto}}
@media (prefers-reduced-motion:reduce){.strip img{transition:none}}
.viewer{border:0;padding:0;margin:0;width:100vw;height:100dvh;max-width:none;
max-height:none;background:#0b0f11;color:#fff}
.viewer::backdrop{background:rgba(8,12,14,.6)}
.viewer[open]{display:grid;grid-template-rows:auto minmax(0,1fr);
grid-template-columns:minmax(0,1fr)}
.viewer .vw-bar{display:flex;align-items:center;gap:12px;padding:10px 14px;
font:500 13.5px/1.3 var(--sans)}
.viewer .vw-bar .what{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.viewer .count{font-family:var(--mono);color:#c9d1d4}
.viewer .vw-bar a{color:#fff}
.viewer .stage{position:relative;display:flex;align-items:center;
justify-content:center;min-height:0;padding:0 64px 16px;touch-action:pan-y}
.viewer .stage img{max-width:100%;max-height:100%;object-fit:contain;
border-radius:4px;user-select:none;-webkit-user-drag:none}
.viewer button{font:600 15px/1 var(--sans);color:#fff;background:rgba(255,255,255,.12);
border:1px solid rgba(255,255,255,.28);border-radius:8px;cursor:pointer;
min-width:44px;min-height:44px}
.viewer button:hover,.viewer button:focus-visible{background:rgba(255,255,255,.24)}
.viewer button:disabled{opacity:.3;cursor:default}
.viewer .prev,.viewer .next{position:absolute;top:50%;transform:translateY(-50%);
font-size:24px}
.viewer .prev{left:10px}.viewer .next{right:10px}
@media (max-width:600px){.viewer .stage{padding:0 8px 64px}
.viewer .prev,.viewer .next{top:auto;bottom:10px;transform:none}}
"""

# The gallery's viewer. Without JavaScript each image is a plain link to the
# full-size file; with it, selecting an image opens it in a dialog that steps
# through the images of the same vignette (arrow keys, buttons or a swipe).
VIEWER = """<dialog class='viewer' id='viewer' aria-label='Image viewer'>
<div class='vw-bar'><span class='what' id='vw-what'></span>
<span class='count' id='vw-count'></span>
<a id='vw-full' href='#' target='_blank' rel='noopener'>Full size</a>
<button type='button' class='close' id='vw-close' aria-label='Close (Esc)'>&times;</button></div>
<div class='stage' id='vw-stage'>
<button type='button' class='prev' id='vw-prev' aria-label='Previous image (left arrow)'>&lsaquo;</button>
<img id='vw-img' alt=''>
<button type='button' class='next' id='vw-next' aria-label='Next image (right arrow)'>&rsaquo;</button>
</div></dialog>
<script>
(function(){
var d=document.getElementById('viewer');
if(!d||!d.showModal)return;
var img=document.getElementById('vw-img'),what=document.getElementById('vw-what'),
count=document.getElementById('vw-count'),full=document.getElementById('vw-full'),
prev=document.getElementById('vw-prev'),next=document.getElementById('vw-next'),
set=[],at=0,title='';
function show(i){
  at=Math.max(0,Math.min(set.length-1,i));
  var a=set[at],t=a.querySelector('img');
  img.src=a.href;img.alt=t?t.alt:'';
  var cap=a.parentNode.querySelector('figcaption');
  what.textContent=title+(cap?' \u2014 '+cap.textContent:'');
  count.textContent=set.length>1?(at+1)+' / '+set.length:'';
  full.href=a.href;
  prev.disabled=at===0;next.disabled=at===set.length-1;
  prev.hidden=next.hidden=set.length<2;
  [at-1,at+1].forEach(function(j){if(set[j])(new Image()).src=set[j].href;});
}
document.addEventListener('click',function(e){
  var a=e.target.closest&&e.target.closest('.frames a');
  if(!a||e.ctrlKey||e.metaKey||e.shiftKey||e.button)return;
  e.preventDefault();
  var box=a.closest('.frames'),card=a.closest('.vig');
  set=[].slice.call(box.querySelectorAll('a'));
  var h=card&&card.querySelector('h3');title='';
  if(h){h=h.cloneNode(true);[].forEach.call(h.querySelectorAll('.muted'),
    function(m){m.remove();});title=h.textContent.trim();}
  show(set.indexOf(a));d.showModal();
});
prev.onclick=function(){show(at-1);};next.onclick=function(){show(at+1);};
document.getElementById('vw-close').onclick=function(){d.close();};
d.addEventListener('keydown',function(e){
  if(e.key==='ArrowLeft'){show(at-1);e.preventDefault();}
  else if(e.key==='ArrowRight'){show(at+1);e.preventDefault();}
  else if(e.key==='Home'){show(0);e.preventDefault();}
  else if(e.key==='End'){show(set.length-1);e.preventDefault();}
});
d.addEventListener('click',function(e){if(e.target===d||e.target.id==='vw-stage')d.close();});
d.addEventListener('close',function(){img.removeAttribute('src');if(set[at])set[at].focus();});
var x0=null;
d.addEventListener('pointerdown',function(e){x0=e.pointerType==='mouse'?null:e.clientX;});
d.addEventListener('pointerup',function(e){
  if(x0===null)return;var dx=e.clientX-x0;x0=null;
  if(Math.abs(dx)>50)show(at+(dx<0?1:-1));
});
})();
</script>"""

COPY_SCRIPT = """<script>
var b=document.getElementById('copybtn');
if(b){b.addEventListener('click',function(){var c=document.getElementById('dockercmd');
function sel(){var r=document.createRange();r.selectNodeContents(c);
getSelection().removeAllRanges();getSelection().addRange(r);b.textContent='Selected';}
try{navigator.clipboard.writeText(c.textContent).then(function(){b.textContent='Copied';},sel);}
catch(e){sel();}});}
</script>"""


def page(title, body, footer, here, script=""):
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>{0}</title>{5}<style>{1}{2}</style></head><body>{6}<main>{3}"
        "<footer>{4}</footer></main>{7}</body></html>"
    ).format(
        esc(title),
        css(),
        SITE_CSS,
        body,
        footer,
        dashboard.FONTS,
        site_header(here, "../" if here == "gallery" else ""),
        script,
    )


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
            entries = sorted(os.listdir(base), key=natural_key)
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


def anchor(tool, n):
    """The gallery anchor of one tool's vignette: paraview-ex03."""
    return "{0}-ex{1:02d}".format(tool.lower(), n)


def render_gallery(found, placed, with_results=None):
    """ParaView ex00 to ex12, then VisIt ex00 to ex12; frames in order.

    with_results: the vignettes the dashboard has a page for (those with
    records); others get no Results link. None: link every vignette.
    """
    numbers = sorted(found)
    tocs, sections = [], []
    for tool, suite in SUITES:
        mine = [n for n in numbers if tool in found[n]["dir"]]
        if not mine:
            continue
        tocs.append(
            "<nav class='toc'><b>{0}</b>{1}</nav>".format(
                esc(tool),
                "".join(
                    "<a href='#{0}'>ex{1:02d} {2}</a>".format(
                        anchor(tool, n), n, esc(describe(n, found[n])[0])
                    )
                    for n in mine
                ),
            )
        )
        cards = []
        for n in mine:
            entry = found[n]
            title, about = describe(n, entry)
            name = entry["dir"][tool]
            sites = entry["sites"].get(tool, 0)
            extra = (
                " <span class='muted'>(+{0} site-specific set{1})</span>".format(
                    sites, "" if sites == 1 else "s"
                )
                if sites
                else ""
            )
            results = (
                "<a href='../dashboard/{0}'>Results</a> &middot; ".format(
                    url(dashboard.vignette_page(name))
                )
                if with_results is None or name in with_results
                else ""
            )
            cards.append(
                "<section class='card vig' id='{0}'><h3>{1} ex{2:02d} {3}{4}</h3>"
                "<p class='note'>{5} {6}"
                "<a href='{7}/tree/master/{8}/{9}'>source</a></p>{10}</section>".format(
                    anchor(tool, n),
                    esc(tool),
                    n,
                    esc(title),
                    extra,
                    esc(about),
                    results,
                    REPO_URL,
                    esc(suite),
                    url(name),
                    _frames(entry["images"].get(tool, []), placed, tool, title),
                )
            )
        sections.append(
            "<h2 id='{0}'>{1}</h2>{2}".format(
                esc(tool.lower()), esc(tool), "".join(cards)
            )
        )
    body = (
        "<p class='eyebrow'>Gallery</p><h1>What each vignette draws</h1>"
        "<p class='lede'>The baseline images the regression suite compares every "
        "run against, ParaView first, then VisIt, in vignette order. Select an image "
        "to view it large, then step through that vignette's images with the arrow "
        "keys, the &lsaquo; &rsaquo; buttons or a swipe; Esc closes it.</p>{0}{1}"
    ).format("".join(tocs), "".join(sections))
    footer = (
        "Built from the Testing/Baseline images in jameskress/Visualization_Vignettes "
        "by Testing/site_pages.py. Results of every run: "
        "<a href='../dashboard/'>dashboard</a>."
    )
    return page("Gallery - Visualization Vignettes", body, footer, "gallery", VIEWER)


# The landing page's strip: one image of each, in order, ParaView then VisIt.
HERO = (
    ("ParaView", 3),
    ("ParaView", 4),
    ("ParaView", 6),
    ("ParaView", 9),
    ("VisIt", 2),
    ("VisIt", 6),
    ("VisIt", 10),
    ("VisIt", 12),
)


def hero_images(found, placed):
    picks = []
    for tool, n in sorted(HERO, key=lambda h: (TOOLS.index(h[0]), h[1])):
        paths = found.get(n, {}).get("images", {}).get(tool) or []
        if not paths:
            continue
        title = describe(n, found[n])[0]
        # The middle frame: a sequence's first frame is often sparse.
        middle = paths[len(paths) // 2]
        label = "{0} ex{1:02d} {2}".format(tool, n, title)
        picks.append(
            "<a href='gallery/#{0}' title='{1}: open in the gallery'><img src='gallery/{2}' "
            "loading='lazy' alt='{1} baseline image'><span>{1}</span></a>".format(
                anchor(tool, n), esc(label), url(placed[middle][1])
            )
        )
    return "<div class='strip'>{0}</div>".format("".join(picks)) if picks else ""


def headline(repo):
    """The landing page's numbers, from the committed records."""
    histories = dashboard.publish_names(dashboard.load_histories(repo))
    now = datetime.datetime.now()
    retired = {
        dashboard.public_text(c): e for c, e in dashboard.load_retired(repo).items()
    }
    states = {
        key: dashboard.config_state(key[1], vs, now, retired.get(key[0]))
        for key, vs in histories.items()
    }
    active = {c for (c, t), st in states.items() if not st["retired"]}
    counts = [st["counts"] for st in states.values() if not st["retired"]]
    versions = {
        tool: sorted(
            {
                dashboard.drift.tool_version(rec)
                for (_, t), vs in histories.items()
                if t == tool
                for rows in vs.values()
                for _, rec in rows
                if dashboard.drift.tool_version(rec)
            },
            key=dashboard.version_key,
        )
        for tool in TOOLS
    }
    first = min(
        (ts for vs in histories.values() for rows in vs.values() for ts, _ in rows),
        default="",
    )
    return {
        "with_results": {v for vs in histories.values() for v in vs},
        "vignettes": len({v for vs in histories.values() for v in vs}),
        "configurations": len(active),
        "sites": len({dashboard.site_of(c) for c in active} - {"Other"}),
        "versions": versions,
        "passing": sum(c["pass"] for c in counts),
        "results": sum(sum(c.values()) for c in counts),
        "records": sum(len(rows) for vs in histories.values() for rows in vs.values()),
        "since": first[:7],
    }


DOCKER_CMD = (
    'mkdir "$HOME/vv-try" && docker run --rm -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) '
    '-v "$HOME/vv-try:/work" ghcr.io/jameskress/visualization_vignettes:latest bash -c '
    "'cd /work && cp -r /app/Testing /app/data . && mkdir -p ParaView_Vignettes && "
    "cp -r /app/ParaView_Vignettes/ex01_pvScreenshot ParaView_Vignettes/ && pvbatch "
    "--force-offscreen-rendering ParaView_Vignettes/ex01_pvScreenshot/ex01_pvScreenshot.py'"
)


def render_landing(found, placed, numbers):
    pv, vi = numbers["versions"]["ParaView"], numbers["versions"]["VisIt"]
    stats = [
        (numbers["vignettes"], "vignettes, the same 13 in each tool"),
        (
            numbers["configurations"],
            "machine configurations at {0} sites".format(numbers["sites"]),
        ),
        (
            len(pv) + len(vi),
            "tool versions tracked: ParaView {0} to {1}, VisIt {2} to {3}".format(
                pv[0] if pv else "-",
                pv[-1] if pv else "-",
                vi[0] if vi else "-",
                vi[-1] if vi else "-",
            ),
        ),
        (
            "{0:.1f}%".format(100.0 * numbers["passing"] / numbers["results"])
            if numbers["results"]
            else "-",
            "{0} of {1} latest results pass".format(
                numbers["passing"], numbers["results"]
            ),
        ),
    ]
    stat_html = "".join(
        "<div class='stat'><div class='v'>{0}</div><div class='k'>{1}</div></div>".format(
            esc(v), esc(k)
        )
        for v, k in stats
    ) + (
        "<div class='stat wide'><div class='k'>{0:,} recorded runs since {1}, every "
        "one public in the repository.</div></div>".format(
            numbers["records"], esc(numbers["since"])
        )
    )

    def item(n):
        return (
            "<li><span class='n'>ex{0:02d}</span><span>{1}<br><span class='d'>{2}"
            "</span></span></li>".format(n, esc(ABOUT[n][0]), esc(ABOUT[n][1]))
        )

    body = """
<section class='hero' style='margin-top:8px'>
 <div>
  <p class='eyebrow'>ParaView &middot; VisIt &middot; in situ &middot; HPC</p>
  <h1>Small, tested examples of scientific visualization, from a laptop to a
  supercomputer</h1>
  <p class='lede'>Visualization Vignettes is a cookbook of runnable ParaView and VisIt
  scripts, batch scripts for real clusters, and an in situ miniapp. Every vignette is
  also a regression test, run on each site and tool version, so you can see that it
  still works and how fast it runs.</p>
  <p class='who'><b>For</b> researchers and students learning to visualize large data
  on HPC systems, <b>for</b> HPC centres checking a new ParaView or VisIt build, and
  <b>for</b> developers of in situ tools.</p>
  <div class='btns'><a class='btn primary' href='#try'>Run a vignette in two
  minutes</a><a class='btn ghost' href='dashboard/'>Browse the results</a></div>
 </div>
 <div class='stats'>{stats}</div>
</section>
<section>{strip}<p class='note' style='margin-top:8px'>The baseline images every run is
compared against, ParaView then VisIt. Select one to open it in the gallery.</p></section>
<section id='try'>
 <p class='eyebrow'>Start here</p><h2>What you can do</h2>
 <div class='ctas'>
  <div class='card cta span2'><span class='tag'>2 minutes &middot; Docker</span>
   <h3>Run a vignette</h3>
   <p>Pulls the published image (ParaView {pin}, about 4.5 GB) and renders
   <code>ex01_pvScreenshot</code> into a new folder, <code>~/vv-try</code>. Linux or
   macOS:</p>
   <div class='cmd'><code id='dockercmd'>{docker}</code><button type='button'
   id='copybtn'>Copy</button></div>
   <p>The folder must not exist yet, so nothing is overwritten. To try again after
   a failed pull, use another name in both places, or remove the empty folder.</p>
   <a class='go' href='https://codespaces.new/jameskress/Visualization_Vignettes?quickstart=1'>Or
   open it in GitHub Codespaces &rarr;</a></div>
  <a class='card cta' href='dashboard/'><span class='tag'>Results</span>
   <h3>Browse the dashboard</h3><p>The latest result of every vignette on every
   machine, what each tool upgrade changed, and each machine's history.</p>
   <span class='go'>Open the dashboard &rarr;</span></a>
  <a class='card cta' href='gallery/'><span class='tag'>Gallery</span>
   <h3>See what each vignette draws</h3><p>Every baseline image, ParaView then VisIt,
   in vignette order.</p><span class='go'>Open the gallery &rarr;</span></a>
  <a class='card cta' href='{blob}Testing/ADD_YOUR_SITE.md'><span class='tag'>Contribute</span>
   <h3>Add your site</h3><p>Run the suite on your workstation or cluster and send the
   results in a pull request. A check keeps names public and records valid.</p>
   <span class='go'>Read the guide &rarr;</span></a>
  <a class='card cta' href='{blob}Miniapps/gray-scott/README.md'><span class='tag'>In situ</span>
   <h3>Gray-Scott miniapp</h3><p>A reaction-diffusion simulation that renders while it
   runs, with Ascent, Catalyst2, ADIOS2 and Kombyne back ends.</p>
   <span class='go'>Open the miniapp &rarr;</span></a>
  <a class='card cta full' href='{blob}CITATION.cff'><span class='tag'>Cite</span>
   <h3>Cite Visualization Vignettes</h3><p>Citation metadata is in
   <code>CITATION.cff</code>; GitHub's "Cite this repository" button gives BibTeX and
   APA. A Zenodo DOI comes with release 1.1.0.</p>
   <span class='go'>Get the citation &rarr;</span></a>
 </div>
</section>
<section>
 <p class='eyebrow'>What's inside</p><h2>Thirteen vignettes in each tool, and in situ
 examples</h2>
 <p class='note'>Each number is the same exercise in ParaView and in VisIt, with batch
 scripts for Ibex and Shaheen. ex00 to ex06 show how to do a thing; ex07 to ex12 check
 that a thing still works and fail the suite when it changes.</p>
 <div class='inside'>
  <div class='card'><h3>How to do a thing</h3><ol>{how}</ol></div>
  <div class='card'><h3>Checks that it still works</h3><ol>{checks}</ol></div>
  <div class='card'><h3>In situ</h3>
   <div class='kind'>Miniapp</div><p class='note'>Gray-Scott reaction-diffusion, C++
   and MPI, rendering in situ or in transit.</p>
   <div class='kind'>Back ends</div><p class='note'>Ascent, Catalyst2 (ParaView),
   ADIOS2, Kombyne.</p>
   <div class='kind'>Vignettes</div><p class='note'><code>is00</code> zero-copy
   adapter: hand a simulation's arrays to a visualization library without copying.</p>
   <div class='kind'>Runs on</div><p class='note'>Docker, Codespaces, a workstation,
   Ibex and Shaheen III.</p></div>
 </div>
</section>""".format(
        stats=stat_html,
        strip=hero_images(found, placed),
        pin=esc(dashboard.CURRENT_PINS["ParaView"]),
        docker=esc(DOCKER_CMD),
        blob=REPO_URL + "/blob/master/",
        how="".join(item(n) for n in range(0, 7)),
        checks="".join(item(n) for n in range(7, 13)),
    )
    footer = (
        "Built by Testing/site_pages.py from "
        "<a href='{0}'>jameskress/Visualization_Vignettes</a>.".format(REPO_URL)
    )
    return page("Visualization Vignettes", body, footer, "home", COPY_SCRIPT)


def build(out, repo=REPO_ROOT):
    found = baselines(repo)
    gallery = os.path.join(out, "gallery")
    root = os.path.join(out, "root")
    for directory in (gallery, root):
        shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory)
    placed = copy_images(found, gallery, repo)
    for directory in (gallery, root):
        dashboard.copy_logo(directory, repo)
    numbers = headline(repo)
    with open(os.path.join(gallery, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_gallery(found, placed, numbers["with_results"]))
    # The landing page links its strip into the gallery beside it.
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_landing(found, placed, numbers))
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

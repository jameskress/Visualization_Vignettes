"""The speed index: every machine at every version, against one typical run.

For each vignette, the *typical run* is the median, over every (machine,
version) pair, of that pair's median measurement, from runs of the
vignette's newest code. A cell (one machine at one version) is the geometric
mean over vignettes of its median divided by the typical run, so 1x is a
typical run of the suite, 1.25x is 25% more and 0.8x is 20% less. Each
vignette counts the same, whatever its length: ex06's minutes do not drown
out a two-second vignette (the SPEC and LNT convention).

Three rules keep a cell honest (what Codespeed, ASV, Perfherder and LNT do):

* Noise. A cell is coloured only when its 95% bootstrap interval, from
  resampling each vignette's repeated runs, leaves out 1x. With one run per
  vignette there is no interval, and the cell is shown but never coloured.
* Like for like. A row (one machine) is averaged over the vignettes its
  newest version ran; an older version that lacks one of them is marked, and
  its cell covers only the ones it has.
* A fixed baseline. The typical run comes from the records up to
  REFERENCE_UNTIL, so adding a machine or a run does not move every cell.
  It is moved on purpose (at a release), and the page states its date. A
  measure or vignette with no records before then uses every record, and the
  page says so.

Standard library only: dashboard.py imports this to build the index page.
"""

import datetime
import math
import random
import statistics

import drift

# The typical run is computed from records before this day (local time, as
# the records are). Move it on purpose, with a note in the release.
REFERENCE_UNTIL = datetime.datetime(2026, 11, 24)

# What the index can be built from, lower better for all: (record key,
# label, unit). CPU time is summed over whatever processes the record's
# scope covers (the ranks and the harness on every machine).
MEASURES = (
    ("execution_time", "Time", "s"),
    ("cpu_seconds", "CPU time", "s"),
    ("memory_usage_mb", "Peak memory (PSS)", "MB"),
    ("energy_joules", "Node energy", "J"),
    ("gpu_energy_joules", "GPU energy", "J"),
)

# Memory is measured several ways (memory_measurement_scope); only the
# proportional set size of the processes doing the work means the same thing
# on every machine. Slurm-sampled figures are left out of the memory index.
MEMORY_SCOPES = ("srun-step-pss-single-node", "child-tree-pss")

BOOTSTRAP = 300
BAND = 0.05  # within 5% of typical is never coloured


def last_day(until=REFERENCE_UNTIL):
    """'23 Nov 2026': the last day whose records the typical run uses."""
    return (until - datetime.timedelta(days=1)).strftime("%d %b %Y").lstrip("0")


def _value(measure, record):
    value = record.get(measure)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    if measure == "memory_usage_mb":
        if record.get("memory_measurement_scope") not in MEMORY_SCOPES:
            return None
    elif not drift.comparable(measure, record):
        return None
    return float(value)


def _when(ts):
    try:
        return datetime.datetime.fromisoformat(ts[:19])
    except (TypeError, ValueError):
        return None


def collect(histories, tool, retired, run_ok, measure):
    """{(config, vignette, version): [(when, value)]} at each vignette's newest code."""
    newest = {}
    for (config, t), vignettes in histories.items():
        if t != tool or config in retired:
            continue
        for vignette, rows in vignettes.items():
            for _, rec in rows:
                newest[vignette] = max(newest.get(vignette, 0), rec.get("_rev", 0))
    out = {}
    for (config, t), vignettes in histories.items():
        if t != tool or config in retired:
            continue
        for vignette, rows in vignettes.items():
            for ts, rec in rows:
                version = drift.tool_version(rec)
                value = _value(measure, rec)
                if (
                    version
                    and value is not None
                    and run_ok(rec)
                    and rec.get("_rev", 0) == newest[vignette]
                ):
                    out.setdefault((config, vignette, version), []).append(
                        (_when(ts), value)
                    )
    return out


def references(samples, until=REFERENCE_UNTIL):
    """({vignette: typical value}, {vignettes whose typical run is not frozen})."""
    frozen, every = {}, {}
    for (config, vignette, version), runs in samples.items():
        before = [v for when, v in runs if when is not None and when < until]
        if before:
            frozen.setdefault(vignette, []).append(statistics.median(before))
        every.setdefault(vignette, []).append(statistics.median(v for _, v in runs))
    refs, moving = {}, set()
    for vignette, medians in every.items():
        if vignette in frozen:
            refs[vignette] = statistics.median(frozen[vignette])
        else:
            refs[vignette] = statistics.median(medians)
            moving.add(vignette)
    return refs, moving


def _interval(draws):
    draws = sorted(draws)
    lo = draws[int(0.025 * (len(draws) - 1))]
    hi = draws[int(math.ceil(0.975 * (len(draws) - 1)))]
    return lo, hi


def cell(runs_by_vignette, refs, rng):
    """(index, low, high) for one machine at one version; low/high None when
    every vignette has a single run."""
    names = sorted(runs_by_vignette)
    logs = [math.log(statistics.median(runs_by_vignette[v]) / refs[v]) for v in names]
    index = math.exp(sum(logs) / len(logs))
    if all(len(runs_by_vignette[v]) < 2 for v in names):
        return index, None, None
    draws = []
    for _ in range(BOOTSTRAP):
        total = 0.0
        for v in names:
            runs = runs_by_vignette[v]
            pick = [runs[rng.randrange(len(runs))] for _ in runs]
            total += math.log(statistics.median(pick) / refs[v])
        draws.append(math.exp(total / len(names)))
    lo, hi = _interval(draws)
    return index, lo, hi


def one(runs, rng):
    """(median, low, high) of one vignette's runs; low/high None for one run."""
    median = statistics.median(runs)
    if len(runs) < 2:
        return median, None, None
    draws = [
        statistics.median([runs[rng.randrange(len(runs))] for _ in runs])
        for _ in range(BOOTSTRAP)
    ]
    lo, hi = _interval(draws)
    return median, lo, hi


def build(histories, tool, retired, run_ok, version_key, order, until=REFERENCE_UNTIL):
    """Everything the page needs for one tool, as JSON-ready data."""
    out = {"measures": {}, "until": last_day(until)}
    configs, versions = set(), set()
    for measure, label, unit in MEASURES:
        samples = collect(histories, tool, retired, run_ok, measure)
        if not samples:
            continue
        refs, moving = references(samples, until)
        by_cell = {}
        for (config, vignette, version), runs in samples.items():
            by_cell.setdefault((config, version), {})[vignette] = [v for _, v in runs]
        # A row is averaged over the vignettes its newest version ran.
        newest = {}
        for config, version in by_cell:
            if config not in newest or version_key(version) > version_key(
                newest[config]
            ):
                newest[config] = version
        row_set = {c: set(by_cell[(c, v)]) for c, v in newest.items()}
        rng = random.Random("{0}|{1}".format(tool, measure))
        cells = []
        for (config, version), runs_by in sorted(by_cell.items()):
            mine = {v: r for v, r in runs_by.items() if v in row_set[config]}
            if not mine:
                continue
            index, lo, hi = cell(mine, refs, rng)
            per = {}
            for vignette, runs in sorted(runs_by.items()):
                median, plo, phi = one(runs, rng)
                per[vignette] = [
                    round(median, 4),
                    None if plo is None else round(plo, 4),
                    None if phi is None else round(phi, 4),
                    len(runs),
                ]
            cells.append(
                {
                    "c": config,
                    "v": version,
                    "i": round(index, 4),
                    "lo": None if lo is None else round(lo, 4),
                    "hi": None if hi is None else round(hi, 4),
                    "n": len(mine),
                    "of": len(row_set[config]),
                    "runs": sum(len(r) for r in mine.values()),
                    "per": per,
                }
            )
            configs.add(config)
            versions.add(version)
        out["measures"][measure] = {
            "label": label,
            "unit": unit,
            "refs": {v: round(r, 4) for v, r in sorted(refs.items())},
            "moving": sorted(moving),
            "rows": {c: len(s) for c, s in row_set.items()},
            "cells": cells,
        }
    out["configs"] = sorted(configs, key=order)
    out["versions"] = sorted(versions, key=version_key)
    return out


def colour(ratio, lo, hi):
    """The five-step class of a ratio, '' within the noise, 'one' untestable.

    The same rule the page's script applies; kept here so tests can pin it.
    """
    if lo is None:
        return "one"
    if lo <= 1.0 <= hi or abs(ratio - 1.0) < BAND:
        return ""
    if ratio < 0.8:
        return "fast2"
    if ratio < 1.0:
        return "fast1"
    if ratio <= 1.25:
        return "slow1"
    return "slow2"


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
SECTION = """
<section><h2>Every machine, every version</h2>
<p class='note'>Each cell is one machine with one tool version, against <b>the
typical run</b>: for each vignette, the median of every machine-and-version's
median, from the records up to <span class='si-until'></span>. 1&times; is that
typical run, 1.25&times; is 25% more (slower, or more memory or energy), 0.8&times;
is 20% less. The baseline is the same for every cell; it is not any one machine and
not the default version. Read across a row for what each upgrade did on that
machine; read down a column to compare machines at one version.</p>
{blocks}
<details class='card si-how'><summary><b>How the index is computed</b></summary><dl>
<dt>Which runs</dt><dd>Only runs of each vignette's newest code, so every run
compared measured the same test, and only runs that finished.</dd>
<dt>Typical run</dt><dd>The baseline for every number and colour here. Per vignette:
each machine-and-version's median, then the median of those. It is computed from the
records up to the stated date and kept there, so a new machine or run does not move
every cell; it is moved on purpose, at a release. A measure or vignette with no
records before that date uses all of them, and says so.</dd>
<dt>Cell, all vignettes</dt><dd>The geometric mean, over the vignettes, of the
machine's median divided by the typical run, so each vignette counts the same
whatever its length. A row is averaged over the vignettes its newest version ran; an
older version that lacks some is marked with a corner tick and covers only the ones
it has.</dd>
<dt>Colour</dt><dd>Only when the change is beyond the noise: resampling each
vignette's repeated runs 300 times gives a 95% range, and the cell is coloured when
that range leaves out 1&times; and the cell is at least 5% from it. A dotted number
had one run per vignette, so its noise is unknown.</dd>
<dt>Peak memory</dt><dd>Only runs measured as PSS, the memory the processes doing
the work hold, which means the same on every machine. Slurm-sampled memory is left
out.</dd>
<dt>Energy</dt><dd>Node energy where the node's own counters are readable (Shaheen
CPU nodes); GPU energy, the GPUs alone, wherever nvidia-smi is.</dd>
</dl></details>
</section>
"""

BLOCK = """
<div data-tool='{tool}' class='si' data-si='{tool}'>
<div class='controls js-only'>
<label class='inline'>Measure <select class='si-measure'></select></label>
<label class='inline'>Vignettes <select class='si-vig'></select></label>
</div>
<h3 class='si-title'></h3>
<div class='card'><div class='scroll'><table class='matrix si-grid'></table></div>
<div class='key'>
<span><i class='fast2'></i>more than 20% below typical</span>
<span><i class='fast1'></i>5 to 20% below</span>
<span><i class='plain'></i>within the noise, or within 5%</span>
<span><i class='slow1'></i>5 to 25% above</span>
<span><i class='slow2'></i>more than 25% above</span>
<span class='one'>1.12&times;</span><span>dotted: one run per vignette, noise unknown</span>
<span><b class='si-part'>&#x25E4;</b> covers fewer vignettes than its row</span>
<span><span class='n'>(12 of 13)</span> the row covers 12 of the 13 vignettes</span>
</div></div>
<h4 class='sub-h'>The same, as lines</h4>
<p class='note si-lineintro'></p>
<div class='card'><div class='legend si-legend'></div>
<svg class='chart wide si-lines' role='img'></svg></div>
<p class='note si-moving'></p>
</div>
"""

CSS = """
#tip{white-space:pre-line}
.si .key .one{text-decoration:underline dotted var(--muted);text-underline-offset:3px;
font:12.5px var(--mono)}
.si td.c a{text-decoration:none;color:inherit;display:block;position:relative}
.si td.c a:hover span{box-shadow:inset 0 0 0 2px var(--ink)}
.si td.c a.part::after{content:"";position:absolute;top:2px;left:2px;border-style:solid;
border-width:7px 7px 0 0;border-color:var(--ink2) transparent transparent transparent}
.si-part{color:var(--ink2);font-size:11px}
.si th.vh{font-weight:500;color:var(--ink2);font-size:12.5px;padding:4px 6px}
.si-how{margin-top:16px}.si-how dl{display:grid;grid-template-columns:9rem minmax(0,1fr);
gap:6px 14px;font-size:13.5px;margin:10px 0 0;max-width:86ch}
.si-how dt{font-weight:600}.si-how dd{margin:0;color:var(--ink2)}
@media (max-width:520px){.si-how dl{grid-template-columns:minmax(0,1fr)}}
.si svg .grid{stroke:var(--grid)}
.si svg .one-line{stroke:var(--ink2);stroke-dasharray:4 3}
.si svg .atitle{fill:var(--ink2);font-size:12px;font-weight:500}
.si svg text{font-size:11px;fill:var(--muted)}
.legend{display:flex;gap:4px 16px;flex-wrap:wrap;font-size:13px;color:var(--ink2);
margin:0 0 8px}
"""

SCRIPT = r"""
<script type='application/json' id='si-data'>__SI_DATA__</script>
<script>
(function(){
var ALL=JSON.parse(document.getElementById('si-data').textContent);
var SITES=['Workstation','Ibex','Shaheen','Other'];
var NS='http://www.w3.org/2000/svg';
function el(tag,attrs,parent){var n=document.createElementNS(NS,tag);
 for(var k in attrs){n.setAttribute(k,attrs[k]);}if(parent){parent.appendChild(n);}return n;}
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;',
 '<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function slot(site){var i=SITES.indexOf(site);return 'var(--s'+(i<0?3:i)+')';}
function vname(v){return v.slice(0,4)+' '+(ALL.about[v]||v);}
function pct(x){return x>=1?Math.round((x-1)*100)+'% above typical':
 Math.round((1-x)*100)+'% below typical';}
function num(x,unit){var a=Math.abs(x);var t=a>=100?Math.round(x):a>=10?x.toFixed(1):
 x.toFixed(2);return t+' '+unit;}
function cls(r,lo,hi){if(lo===null||lo===undefined){return 'one';}
 if((lo<=1&&1<=hi)||Math.abs(r-1)<0.05){return '';}
 return r<0.8?'fast2':r<1?'fast1':r<=1.25?'slow1':'slow2';}
document.querySelectorAll('.si').forEach(function(box){
 var tool=box.dataset.si,D=ALL.tools[tool];if(!D){box.hidden=true;return;}
 var mSel=box.querySelector('.si-measure'),vSel=box.querySelector('.si-vig');
 var M=Object.keys(D.measures)[0],V='all';
 mSel.innerHTML=Object.keys(D.measures).map(function(k){return "<option value='"+k+"'>"+
  esc(D.measures[k].label)+'</option>';}).join('');
 function view(c,m){
  // {r: ratio to typical, lo, hi, text, tip} for one cell in the current view.
  var unit=m.unit,mine;
  if(V==='all'){
   var per=Object.keys(c.per).sort().map(function(v){return '  '+vname(v)+': '+
    num(c.per[v][0],unit)+' (typical '+num(m.refs[v],unit)+')';}).join('\n');
   var range=c.lo===null?'one run per vignette, so the noise is unknown':
    '95% range '+c.lo.toFixed(2)+' to '+c.hi.toFixed(2)+'×';
   return {r:c.i,lo:c.lo,hi:c.hi,text:c.i.toFixed(2)+'×',part:c.n<c.of,
    tip:c.c+' · '+tool+' '+c.v+'\n'+m.label+': '+c.i.toFixed(2)+
     '× the typical run, '+pct(c.i)+'\n'+range+'\n'+c.n+' of the row\'s '+c.of+
     ' vignettes, '+c.runs+' runs\n'+per};}
  var p=c.per[V];if(!p){return null;}
  var ref=m.refs[V],r=p[0]/ref;
  var rng=p[1]===null?'one run, so the noise is unknown':'95% range '+
   num(p[1],unit)+' to '+num(p[2],unit);
  return {r:r,lo:p[1]===null?null:p[1]/ref,hi:p[2]===null?null:p[2]/ref,
   text:num(p[0],unit),part:false,
   tip:c.c+' · '+tool+' '+c.v+' · '+vname(V)+'\nMedian '+num(p[0],unit)+
    ' over '+p[3]+' runs ('+rng+')\nTypical run of this vignette: '+num(ref,unit)+
    ', so this is '+pct(r)};}
 function render(){
  var m=D.measures[M];
  var vigs=Object.keys(m.refs).sort();
  if(V!=='all'&&vigs.indexOf(V)<0){V='all';}
  vSel.innerHTML="<option value='all'>All vignettes combined</option>"+vigs.map(
   function(v){return "<option value='"+v+"'"+(v===V?' selected':'')+'>'+
   esc(vname(v))+'</option>';}).join('');
  mSel.value=M;vSel.value=V;
  box.querySelector('.si-title').textContent=tool+': '+m.label+(V==='all'?
   ', all vignettes':', '+vname(V));
  var cells={};m.cells.forEach(function(c){cells[c.c+'|'+c.v]=c;});
  var versions=D.versions.filter(function(v){return m.cells.some(function(c){
   return c.v===v&&(V==='all'||c.per[V]);});});
  var configs=D.configs.filter(function(k){return m.cells.some(function(c){
   return c.c===k&&(V==='all'||c.per[V]);});});
  var h='<thead><tr><td></td>'+versions.map(function(v){return "<th class='vh'>"+
   esc(tool)+' '+esc(v)+'</th>';}).join('')+'</tr></thead><tbody>';
  configs.forEach(function(k){
   var rowNote=V==='all'&&m.rows[k]<Object.keys(m.refs).length?
    " <span class='n'>("+m.rows[k]+' of '+Object.keys(m.refs).length+')</span>':'';
   h+="<tr><td class='rowh'><span class='swatch s"+(SITES.indexOf(D.sites[k])<0?3:
    SITES.indexOf(D.sites[k]))+"'></span> <a href='"+esc(D.links[k])+"'>"+esc(k)+'</a>'+
    rowNote+'</td>';
   versions.forEach(function(v){var c=cells[k+'|'+v],w=c&&view(c,m);
    if(!w){h+="<td class='c'><span class='none'>·</span></td>";return;}
    var href=V==='all'?D.links[k]:ALL.vlinks[tool][V];
    h+="<td class='c'><a href='"+esc(href)+"'"+(w.part?" class='part'":'')+
     " data-tip='"+esc(w.tip)+"'><span class='"+cls(w.r,w.lo,w.hi)+"'>"+esc(w.text)+
     '</span></a></td>';});
   h+='</tr>';});
  box.querySelector('.si-grid').innerHTML=h+'</tbody>';
  var moving=m.moving.length?(V==='all'?m.moving:m.moving.filter(function(v){
   return v===V;})):[];
  box.querySelector('.si-moving').textContent=moving.length?('Not yet a fixed '+
   'baseline: '+moving.map(vname).join(', ')+' had no '+m.label.toLowerCase()+
   ' records up to '+ALL.until+', so its typical run uses every record and will move '+
   'as runs are added.'):'';
  lines(m,configs,versions);}
 function lines(m,configs,versions){
  var svg=box.querySelector('.si-lines');svg.innerHTML='';
  var W=1000,H=420,L=170,R=190,T=16,B=58;svg.setAttribute('viewBox','0 0 '+W+' '+H);
  var all=V==='all',pts=[];
  m.cells.forEach(function(c){if(configs.indexOf(c.c)<0||versions.indexOf(c.v)<0){return;}
   var w=view(c,m);if(w){pts.push([c,w]);}});
  svg.setAttribute('aria-label',tool+' '+m.label+' by version for every machine');
  if(!pts.length){return;}
  function val(w){return all?w.r:w.r*(m.refs[V]);}
  var vs=pts.map(function(p){return val(p[1]);});
  var mn=Math.min.apply(null,vs),mx=Math.max.apply(null,vs),lo,hi;
  if(all){lo=Math.log(Math.min(0.7,mn)*0.95);hi=Math.log(Math.max(1.45,mx)*1.05);}
  else{var mid=Math.sqrt(mn*mx);lo=Math.log(Math.min(mid/1.6,mn*0.9));
   hi=Math.log(Math.max(mid*1.6,mx*1.1));}
  function vx(v){return L+(W-L-R)*(versions.length<2?0.5:versions.indexOf(v)/
   (versions.length-1));}
  function vy(x){return T+(H-T-B)*(1-(Math.log(x)-lo)/(hi-lo));}
  var ticks=[];
  if(all){ticks=[0.5,0.6,0.7,0.8,0.9,1,1.1,1.25,1.5,2,2.5,3,4];}
  else{var span=hi-lo,steps=span>Math.log(10)?[1,2,5]:span>Math.log(3)?[1,1.5,2,3,5,7]:
   [1,1.2,1.5,2,2.5,3,4,5,6,8];
   for(var e=-3;e<=6;e++){steps.forEach(function(k){ticks.push(+(k*Math.pow(10,e))
    .toPrecision(3));});}}
  ticks=ticks.filter(function(t){return Math.log(t)>=lo&&Math.log(t)<=hi;});
  ticks.forEach(function(t){
   el('line',{x1:L,x2:W-R,y1:vy(t),y2:vy(t),'class':all&&t===1?'one-line':'grid'},svg);
   el('text',{x:L-8,y:vy(t)+4,'text-anchor':'end'},svg).textContent=all?(t===1?
    '1× = typical run':t+'× · '+pct(t).replace(' typical','')):
    num(t,m.unit);});
  versions.forEach(function(v){el('text',{x:vx(v),y:H-36,'text-anchor':'middle'},svg)
   .textContent=v;});
  el('text',{x:(L+W-R)/2,y:H-10,'text-anchor':'middle','class':'atitle'},svg)
   .textContent=tool+' version';
  var yt=el('text',{x:14,y:(T+H-B)/2,'text-anchor':'middle','class':'atitle',
   transform:'rotate(-90 14 '+(T+H-B)/2+')'},svg);
  yt.textContent=all?m.label+' ÷ typical run (log scale)':
   m.label+', median, '+m.unit+' (log scale)';
  var labels=[];
  configs.forEach(function(k){
   var mine=pts.filter(function(p){return p[0].c===k;}).sort(function(a,b){
    return versions.indexOf(a[0].v)-versions.indexOf(b[0].v);});
   if(!mine.length){return;}
   var col=slot(D.sites[k]);
   if(mine.length>1){el('polyline',{points:mine.map(function(p){return vx(p[0].v)+','+
    vy(val(p[1]));}).join(' '),fill:'none',stroke:col,'stroke-width':2,
    'stroke-linejoin':'round'},svg);}
   mine.forEach(function(p){el('circle',{cx:vx(p[0].v),cy:vy(val(p[1])),r:4.5,fill:col,
    stroke:'var(--surface)','stroke-width':1.5,'data-tip':p[1].tip},svg);});
   var last=mine[mine.length-1];
   labels.push({y:vy(val(last[1])),y0:vy(val(last[1])),x0:vx(last[0].v),text:k,col:col});});
  labels.sort(function(a,b){return a.y-b.y;});
  for(var i=1;i<labels.length;i++){if(labels[i].y-labels[i-1].y<13){
   labels[i].y=labels[i-1].y+13;}}
  var over=labels.length?labels[labels.length-1].y-(H-B):0;
  if(over>0){labels.forEach(function(l){l.y-=over;});}
  labels.forEach(function(l){
   el('polyline',{points:(l.x0+6)+','+l.y0+' '+(W-R+14)+','+l.y+' '+(W-R+22)+','+l.y,
    fill:'none',stroke:l.col,'stroke-width':1,opacity:0.55},svg);
   el('text',{x:W-R+26,y:l.y+4,'class':'dlabel'},svg).textContent=l.text;});
  var sites=[];configs.forEach(function(k){if(sites.indexOf(D.sites[k])<0){
   sites.push(D.sites[k]);}});
  sites.sort(function(a,b){return SITES.indexOf(a)-SITES.indexOf(b);});
  box.querySelector('.si-legend').innerHTML=sites.map(function(s){
   return "<span><span class='swatch s"+(SITES.indexOf(s)<0?3:SITES.indexOf(s))+
   "'></span> "+esc(s)+'</span>';}).join('');
  box.querySelector('.si-lineintro').textContent=all?'One line per machine across the '+
   'versions it ran, against the same typical run as the grid (the dashed 1× '+
   'line), on a log scale, so 2× above and 2× below sit the same distance '+
   'from it. A lower line is a machine that needs less; a slope is what an upgrade '+
   'did there.':'One line per machine across the versions it ran: the median, in '+
   m.unit+', on a log scale. A lower line needs less; a slope is what an upgrade '+
   'did there.';}
 mSel.addEventListener('change',function(){M=mSel.value;render();});
 vSel.addEventListener('change',function(){V=vSel.value;render();});
 box.querySelectorAll('.si-until').forEach(function(e){e.textContent=ALL.until;});
 render();});
document.querySelectorAll('.si-until').forEach(function(e){e.textContent=ALL.until;});
})();
</script>
"""


def render(data, esc):
    """The section, its style and its script, for render_index."""
    import json

    blocks = "".join(BLOCK.format(tool=esc(tool)) for tool in data["tools"])
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (
        "<style>" + CSS + "</style>" + SECTION.format(blocks=blocks),
        SCRIPT.replace("__SI_DATA__", payload),
    )

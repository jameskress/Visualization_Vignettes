#!/bin/bash
# Record one tagged run of both suites on this machine, the way the history expects:
# every gate, one record per vignette, ex11 of VisIt under Xvfb.
#
#   export PARAVIEW_PATH=/path/to/paraview/bin VISIT_PATH=/path/to/visit/bin
#   Testing/record_local_run.sh KW61316-2026-10-21 [machine_name]
#
# Run it from a plain terminal on an otherwise idle machine: anything that keeps
# the display GPU busy (a VNC client, an Electron app streaming a chat, a long
# Omniverse session) adds seconds of GLX context creation to every pvbatch and
# the record is then a record of that, not of the machine (21 Oct 2026, section
# 4 of RUNBOOK.md). A record with the same run id is removed first, so re-running
# replaces it.
set -u
RUN_ID=${1:?run id, e.g. KW61316-2026-10-21}
MACHINE=${2:-$(hostname)}
: "${PARAVIEW_PATH:?set PARAVIEW_PATH to the ParaView bin directory}"
: "${VISIT_PATH:?set VISIT_PATH to the VisIt bin directory}"
PV_VERSION=$("$PARAVIEW_PATH/pvbatch" --version 2>/dev/null | awk '{print $NF}')
VISIT_VERSION=$("$VISIT_PATH/visit" -version 2>&1 | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1)   # "The current version of VisIt is 3.4.2."
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" || exit 1
echo "machine=$MACHINE run_id=$RUN_ID paraview=$PV_VERSION visit=$VISIT_VERSION load=$(cut -d' ' -f1-3 /proc/loadavg)"
python3 manage_metrics.py --remove-run "$RUN_ID" -y >/dev/null 2>&1 && echo "removed an earlier record with this id"
echo "=== ParaView $(date)"
python3 test_suite.py ../ --test_type ParaView --paraview_version "$PV_VERSION" --machine_name "$MACHINE" --run-id "$RUN_ID" --timeout 1800 > "record_${RUN_ID}_paraview.log" 2>&1
echo "ParaView exit=$?"
echo "=== VisIt $(date)"
python3 test_suite.py ../ --test_type VisIt --visit_version "$VISIT_VERSION" --machine_name "$MACHINE" --run-id "$RUN_ID" --test_number 0 1 2 3 4 5 6 7 8 9 10 12 --timeout 1800 > "record_${RUN_ID}_visit.log" 2>&1
echo "VisIt exit=$?"
XVFB_SCREEN=1024x1024x24 ../Scripts/run_with_display.sh python3 test_suite.py ../ --test_type VisIt --visit_version "$VISIT_VERSION" --machine_name "$MACHINE" --run-id "$RUN_ID" --test_number 11 --timeout 1800 > "record_${RUN_ID}_visit_ex11.log" 2>&1
echo "VisIt ex11 exit=$?"
for t in ParaView VisIt; do
    python3 - "$t" "$MACHINE" <<'PY'
import json, sys
t, m = sys.argv[1], sys.argv[2]
d = json.load(open("%s_%s_summary_report.json" % (t, m)))
bad = [k for k, v in d["test_results"].items() if not (v["run_succeeded"] and v["image_comparison_passed"] and v["text_comparison_passed"] and v["numeric_comparison_passed"])]
flags = [(list(p)[0], round(p[list(p)[0]]["percent_change"])) for p in (d.get("significant_performance_changes") or [])]
print("%s: %d vignettes, gates failing on %s, performance flags %s" % (t, len(d["test_results"]), bad or "none", flags or "none"))
PY
done
echo "=== done $(date). Review the lines above, then commit the performance_metrics_${MACHINE}.json files."

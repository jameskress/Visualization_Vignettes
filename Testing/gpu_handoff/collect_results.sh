#!/bin/bash
# On the air-gapped target: tar everything a record produced that must come back.
#   bash collect_results.sh /scratch/$USER/vv_gpu_results_2026-11-01
set -e
OUT=${1:?output folder}; REPO=$(cd "$(dirname "$0")/../.." && pwd); mkdir -p "$OUT"
cd "$REPO"
tar czf "$OUT/vv_results.tgz" \
    $(find ParaView_Vignettes VisIt_Vignettes -path "*/Testing/performance_metrics_*.json" -newer Testing/RUNBOOK.md 2>/dev/null) \
    $(find ParaView_Vignettes VisIt_Vignettes -path "*/Testing/Baseline/*/*" -type f 2>/dev/null) \
    $(ls Testing/*_summary_report.json Testing/vv-*.out 2>/dev/null)
git status --short > "$OUT/git_status.txt"; git log --oneline -1 > "$OUT/git_head.txt"
echo "wrote $OUT/vv_results.tgz ($(du -h "$OUT/vv_results.tgz" | cut -f1)); git_status.txt lists every file the runs changed"

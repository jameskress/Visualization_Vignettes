#!/bin/bash
# Per-node telemetry sampler for Paper 2 runs (one task per node, 1 Hz).
# Usage: node_sampler.sh <out_dir> [interval_s]
# Writes <out_dir>/<hostname>.csv until killed. Reads only world-readable
# files: Cray pm_counters (power, energy), /proc (CPU, memory, load) and the
# Slingshot NIC's telemetry counters. A missing source gives empty columns.
out=${1:?usage: node_sampler.sh <out_dir> [interval_s]}
dt=${2:-1}
mkdir -p "$out" || exit 1
host=$(hostname -s)
f="$out/$host.csv"
pm=/sys/cray/pm_counters
nic=/sys/class/cxi/cxi0/device/telemetry
pm_keys="power energy cpu_power cpu_energy memory_power memory_energy cpu0_temp cpu1_temp"
nic_keys="hni_sts_tx_ok_octets hni_sts_rx_ok_octets pct_no_tct_nacks pct_no_mst_nacks pct_no_trs_nacks pct_bad_seq_nacks pct_retry_srb_requests pct_req_blocked_retry pct_retry_mst_get pct_retry_trs_put"
{
  printf "time_s"
  for k in $pm_keys; do printf ",pm_%s" "$k"; done
  printf ",cpu_user,cpu_nice,cpu_system,cpu_idle,cpu_iowait,cpu_irq,cpu_softirq,mem_total_kb,mem_available_kb,load1"
  for k in $nic_keys; do printf ",nic_%s" "$k"; done
  printf "\n"
} > "$f"
trap 'exit 0' TERM INT
while :; do
  line=$(date +%s.%N)
  for k in $pm_keys; do
    v=$(cut -d" " -f1 "$pm/$k" 2>/dev/null); line+=",$v"
  done
  read -r _ u n s i w q sq _ < /proc/stat
  line+=",$u,$n,$s,$i,$w,$q,$sq"
  mt=$(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{print t","a}' /proc/meminfo)
  read -r l1 _ < /proc/loadavg
  line+=",$mt,$l1"
  for k in $nic_keys; do
    v=$(cat "$nic/$k" 2>/dev/null); line+=",${v%%@*}"
  done
  echo "$line" >> "$f"
  sleep "$dt" &
  wait $!
done

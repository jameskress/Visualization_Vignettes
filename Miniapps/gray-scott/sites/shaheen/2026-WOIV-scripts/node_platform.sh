#!/bin/bash
# The hardware and system software of one node, for a run's telemetry
# (--telemetry). Run as one task per node.
#
#   node_platform.sh line   one line per node, key=value: whatever could
#                           differ between nodes or between run days
#   node_platform.sh full   the full detail of this node (lscpu, NUMA, NIC,
#                           OS, libfabric), meant for one node of a run
#
# Read-only: it only reads /proc, /sys and the tools' output.

sysval() { head -1 "$1" 2>/dev/null || true; }
mode=${1:-line}

if [ "$mode" = line ]; then
    cxi=$(cxi_stat 2>/dev/null)
    fw=$(echo "$cxi" | awk -F': ' '/FW Version/{print $2; exit}')
    link=$(echo "$cxi" | awk -F': ' '/Link speed/{print $2; exit}')
    state=$(echo "$cxi" | awk -F': ' '/Link state/{print $2; exit}')
    echo "host=$(hostname)" \
        "kernel=$(uname -r)" \
        "cpu_driver=$(sysval /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver)" \
        "governor=$(sysval /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" \
        "boost=$(sysval /sys/devices/system/cpu/cpufreq/boost)" \
        "cpu_max_khz=$(sysval /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq)" \
        "cpus=$(nproc --all)" \
        "numa_nodes=$(find /sys/devices/system/node -maxdepth 1 -name 'node[0-9]*' 2>/dev/null | wc -l)" \
        "mem_kB=$(awk '/MemTotal/{print $2}' /proc/meminfo)" \
        "hugepages_2M=$(sysval /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages)" \
        "thp=$(sed 's/.*\[\(.*\)\].*/\1/' /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null)" \
        "nic_fw=${fw:-na}" "nic_link=${link:-na}" "nic_state=${state:-na}"
    exit 0
fi

echo "== host: $(hostname)  date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "== uname"; uname -a
echo "== os-release"; cat /etc/os-release 2>/dev/null
echo "== lscpu"; lscpu 2>&1
echo "== numactl -H"; numactl -H 2>&1
echo "== meminfo"; head -5 /proc/meminfo
echo "== cpufreq"
for f in scaling_driver scaling_governor cpuinfo_min_freq cpuinfo_max_freq; do
    echo "$f: $(sysval /sys/devices/system/cpu/cpu0/cpufreq/$f)"
done
echo "boost: $(sysval /sys/devices/system/cpu/cpufreq/boost)"
echo "== cxi_stat"; cxi_stat 2>&1
echo "== fi_info --version"; fi_info --version 2>&1
echo "== slurm"; srun --version 2>&1
echo "== kernel cmdline"; cat /proc/cmdline 2>/dev/null

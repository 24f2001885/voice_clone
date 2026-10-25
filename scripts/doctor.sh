#!/usr/bin/env bash
# ==============================================================================
# scripts/doctor.sh: Host-side pre-flight verification script
# ==============================================================================
set -u

if [ "${DOCTOR_DEBUG:-0}" = "1" ]; then
    set -x
fi

PASS_COUNT=0
FAIL_COUNT=0
WARNING_COUNT=0

print_result() {
    local status="$1"
    local name="$2"
    local hint="$3"
    if [ "$status" = "OK" ]; then
        printf "[  \033[32mOK\033[0m  ] %s\n" "$name"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ "$status" = "WARN" ]; then
        printf "[ \033[33mWARN\033[0m ] %s -> Hint: %s\n" "$name" "$hint"
        WARNING_COUNT=$((WARNING_COUNT + 1))
    else
        printf "[ \033[31mFAIL\033[0m ] %s -> Fix: %s\n" "$name" "$hint"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo "=== VoxClone Pre-Flight Diagnostics ==="

# Check (a): Docker CLI present and daemon reachable
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    print_result "OK" "Docker daemon reachable" ""
else
    print_result "FAIL" "Docker daemon reachable" "Install Docker and ensure the Docker daemon is running."
fi

# Check (b): GPU passthrough inside Docker
if command -v docker >/dev/null 2>&1 && docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
    print_result "OK" "NVIDIA GPU passthrough in Docker" ""
else
    print_result "FAIL" "NVIDIA GPU passthrough in Docker" "Install nvidia-container-toolkit on host and verify NVIDIA drivers."
fi

# Check (c): Total RAM visible to WSL >= 7000 MB
MEM_TOTAL_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
MEM_TOTAL_MB=$((MEM_TOTAL_KB / 1024))
if [ "$MEM_TOTAL_MB" -ge 7000 ]; then
    print_result "OK" "WSL RAM capacity (${MEM_TOTAL_MB} MB >= 7000 MB)" ""
else
    print_result "FAIL" "WSL RAM capacity (${MEM_TOTAL_MB} MB < 7000 MB)" "Configure .wslconfig with [wsl2] memory=8GB and restart WSL via 'wsl --shutdown'."
fi

# Check (d): Free disk space on current directory >= 30 GB
AVAIL_KB=$(df -k . 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [ "$AVAIL_GB" -ge 30 ]; then
    print_result "OK" "Available disk space (${AVAIL_GB} GB >= 30 GB)" ""
else
    print_result "FAIL" "Available disk space (${AVAIL_GB} GB < 30 GB)" "Free up at least 30 GB disk space on the current filesystem."
fi

# Check (e): WSLg PulseAudio socket presence (warning only)
if [ -S "/mnt/wslg/PulseServer" ]; then
    print_result "OK" "WSLg PulseAudio socket detected (/mnt/wslg/PulseServer)" ""
else
    print_result "WARN" "WSLg PulseAudio socket missing" "Windows 11 + WSLg is needed for microphone and speaker playback; file mode still works."
fi

echo "========================================"
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "Pre-flight failed with $FAIL_COUNT error(s). Please address the fixes above."
    exit 1
else
    echo "Pre-flight passed successfully ($PASS_COUNT checks passed, $WARNING_COUNT warnings)."
    exit 0
fi

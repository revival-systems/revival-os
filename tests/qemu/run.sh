#!/usr/bin/env bash
# Runs one ARMv7-A ELF under QEMU's virt board and checks the result.
# Prints one line, "PASS <name>" or "FAIL <name>: <reason>", keeps the full
# console output in <log>, and exits 0 only on PASS.
#
# Usage:
#   tests/qemu/run.sh NAME ELF LOG EXPECT TEXT
#     EXPECT  exit status QEMU must return (0 = semihosting success,
#             1 = semihosting failure), or "timeout": the program must still
#             be running when the time limit ends
#     TEXT    a fixed string the console output must contain
#
# Environment: QEMU (default qemu-system-arm), QEMU_TIMEOUT (seconds,
# default 20), QEMU_MEM (guest RAM, default 64M; only the task-experiment
# measurements raise it, tests/qemu/measure_tasks.sh).
set -euo pipefail

if [ "$#" -ne 5 ]; then
    echo "usage: $0 NAME ELF LOG EXPECT TEXT" >&2
    exit 2
fi
name=$1 elf=$2 log=$3 expect=$4 text=$5
qemu=${QEMU:-qemu-system-arm}
limit=${QEMU_TIMEOUT:-20}
mem=${QEMU_MEM:-64M}

if ! command -v "$qemu" >/dev/null 2>&1; then
    echo "FAIL $name: $qemu not found (install qemu-system-arm; see docs/DEVELOPMENT.md)"
    exit 1
fi
if [ ! -f "$elf" ]; then
    echo "FAIL $name: $elf does not exist (run make build)"
    exit 1
fi

set +e
# -nic none: the images use no network device. Without it, virt adds a default
# virtio-net NIC and QEMU exits 1 before running the guest when that NIC's
# option ROM (efi-virtio.rom, package ipxe-qemu) is not installed.
timeout --kill-after=5 "$limit" "$qemu" \
    -M virt -cpu cortex-a15 -m "$mem" -nic none \
    -nographic -monitor none -serial stdio \
    -semihosting-config enable=on,target=native \
    -kernel "$elf" </dev/null >"$log" 2>&1
status=$?
set -e

if [ "$expect" = timeout ]; then
    if [ "$status" -ne 124 ] && [ "$status" -ne 137 ]; then
        echo "FAIL $name: expected the time limit to stop it, but QEMU exited $status (log: $log)"
        exit 1
    fi
elif [ "$status" -eq 124 ] || [ "$status" -eq 137 ]; then
    echo "FAIL $name: no exit within ${limit}s (log: $log)"
    exit 1
elif [ "$status" -ne "$expect" ]; then
    echo "FAIL $name: QEMU exited $status, expected $expect (log: $log)"
    exit 1
fi

if ! grep -qF -- "$text" "$log"; then
    echo "FAIL $name: output lacks '$text' (log: $log)"
    exit 1
fi
echo "PASS $name"

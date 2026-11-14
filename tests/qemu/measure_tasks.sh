#!/usr/bin/env bash
# Measurements of the emulator-only task experiment (ADR 0003). Not a test
# and not part of make check: it prints figures, which ADR 0003 records with
# the commit that produced them. Emulator figures are not phone figures
# (docs/TESTING.md).
#
#   1. The largest task count that runs: the "many" case with 256-byte stacks
#      for growing task counts, each given enough guest RAM (QEMU_MEM). The
#      image runs with the MMU off at 0x40000000, so it can use at most the
#      3 GiB below 4 GiB.
#   2. Instructions per switch: two runs of the same image shape (capacity
#      1,000) that differ only in yields per task (2 and 4: the compiler
#      unrolls both loops, and their first and last iterations cancel in the
#      difference), each traced one executed instruction at a time;
#      insn_profile.py divides the difference by the extra yields, which
#      cancels start-up and reporting.
#   3. Code and image bytes, from nm and size.
#   4. Run-to-completion jobs (the second experiment): job counts up to
#      10,000,000 (12 bytes a job; the sweep stops there by choice, and a
#      10,000,000-job build takes about 0.8 GB of host memory because the
#      queue is a Rust static), and instructions per job step, by the same
#      trace difference.
#
# Every image is built by the Makefile's own rule ($(QEMU_OUT)/tasks-%.elf),
# with an ad-hoc TASKS_CFG_<name>, so it is built exactly as the tested ones.
#
# Usage (from the repository root, normally through make measure-tasks):
#   tests/qemu/measure_tasks.sh BUILD_DIR
# Environment: MAKE, ARM_BIN and QEMU, as the Makefile passes them.
set -euo pipefail
export LC_ALL=C   # a decimal point in the printed seconds, whatever the host locale

if [ "$#" -ne 1 ]; then
    echo "usage: $0 BUILD_DIR" >&2
    exit 2
fi
build=$1
make=${MAKE:-make}
qemu=${QEMU:-qemu-system-arm}
bin=${ARM_BIN:?ARM_BIN is not set; run this through make measure-tasks}
out="$build/qemu-virt-armv7"
logs="$build/logs"
mkdir -p "$logs"

# image NAME CASE TASKS STACK YIELDS [JOBS]: build tasks-NAME.elf with the Makefile rule.
image() {
    rm -f "$out/tasks-$1.elf"
    "$make" -s --no-print-directory BUILD="$build" "TASKS_CFG_$1=$2 $3 $4 $5 ${6:-}" "$out/tasks-$1.elf" >/dev/null
}

# trace NAME: run tasks-NAME.elf one instruction per translation block, logging each.
trace() {
    timeout --kill-after=5 300 "$qemu" -M virt -cpu cortex-a15 -m 256M -nic none -nographic -monitor none \
        -serial stdio -semihosting-config enable=on,target=native -accel tcg,one-insn-per-tb=on \
        -d exec,nochain -D "$logs/$1.trace" -kernel "$out/tasks-$1.elf" </dev/null >"$logs/$1.log" 2>&1 || true
    "$bin/arm-none-eabi-nm" -S -C --defined-only "$out/tasks-$1.elf" >"$logs/$1.nm"
}

echo "== 1. Task counts: case many, 256-byte stacks (8 + 256 = 264 bytes per task)"
echo "   QEMU seconds are host wall time for the whole run, not phone time."
printf '   %-10s %7s %6s %6s %8s\n' tasks yields ram result seconds
for spec in "1000 100 64M" "10000 10 64M" "100000 10 256M" "1000000 4 512M" \
            "4000000 2 2048M" "8000000 2 3072M" "12000000 2 3072M"; do
    read -r tasks yields ram <<<"$spec"
    name="count-$tasks"
    image "$name" many "$tasks" 256 "$yields"
    start=$(date +%s.%N)
    if QEMU_MEM=$ram QEMU_TIMEOUT=300 tests/qemu/run.sh "$name" "$out/tasks-$name.elf" "$logs/$name.log" 0 \
        "tasks: PASS many ($tasks tasks x $yields yields)" >/dev/null; then
        result=PASS
    else
        result=FAIL
    fi
    end=$(date +%s.%N)
    printf '   %-10s %7s %6s %6s %8.2f\n' "$tasks" "$yields" "$ram" "$result" \
        "$(awk -v a="$start" -v b="$end" 'BEGIN { print b - a }')"
    rm -f "$out/tasks-$name.elf"
done

echo "== 2. Instructions per yield: 1,000 tasks, 2 and then 4 yields each (QEMU instruction trace)"
for y in 2 4; do
    name="insn-y$y"
    image "$name" many 1000 256 "$y"
    trace "$name"
    if ! grep -qF "tasks: PASS many (1000 tasks x $y yields)" "$logs/$name.log"; then
        echo "FAIL $name: the traced run did not pass (log: $logs/$name.log)"
        exit 1
    fi
done
echo "   Per extra yield (2,000 extra yields), by function:"
python3 -I tests/qemu/insn_profile.py "$logs/insn-y2.nm" "$logs/insn-y2.trace" \
    "$logs/insn-y4.nm" "$logs/insn-y4.trace" 2000 | sed 's/^/   /'
rm -f "$logs"/insn-y*.trace

echo "== 3. Bytes (capacity 1,000 image)"
echo "   Scheduler code, by function (nm -S):"
"$bin/arm-none-eabi-nm" -S -C --defined-only "$out/tasks-insn-y4.elf" \
    | grep -E ' (ctx_switch|task_trampoline|task_exited|tasks::(yield_now|spawn|run|fault|sched_init))$' \
    | while read -r _ size _ symbol; do printf '   %6d  %s\n' "$((16#$size))" "$symbol"; done
echo "   Image sections (size -A):"
"$bin/arm-none-eabi-size" -A -d "$out/tasks-insn-y4.elf" \
    | grep -E '^\.(text|rodata|ARM\.exidx|data|bss|stack|task_arena) ' | sed 's/^/   /'

echo "== 4. Jobs: case jobs many, one runner task (512-byte stack), 12 bytes per queued job"
printf '   %-10s %7s %6s %6s %8s\n' jobs steps ram result seconds
for spec in "1000 100 64M" "100000 10 64M" "1000000 4 256M" "10000000 2 512M"; do
    read -r jobs steps ram <<<"$spec"
    name="jobs-$jobs"
    image "$name" jobs_many 4 512 "$steps" "$jobs"
    start=$(date +%s.%N)
    if QEMU_MEM=$ram QEMU_TIMEOUT=300 tests/qemu/run.sh "$name" "$out/tasks-$name.elf" "$logs/$name.log" 0 \
        "tasks: PASS jobs many ($jobs jobs x $steps steps)" >/dev/null; then
        result=PASS
    else
        result=FAIL
    fi
    end=$(date +%s.%N)
    printf '   %-10s %7s %6s %6s %8.2f\n' "$jobs" "$steps" "$ram" "$result" \
        "$(awk -v a="$start" -v b="$end" 'BEGIN { print b - a }')"
    rm -f "$out/tasks-$name.elf"
done
echo "   Per extra job step (1,000 jobs, 2 and then 4 steps each; 2,000 extra steps), by function:"
for y in 2 4; do
    name="jobs-insn-y$y"
    image "$name" jobs_many 4 512 "$y" 1000
    trace "$name"
    if ! grep -qF "tasks: PASS jobs many (1000 jobs x $y steps)" "$logs/$name.log"; then
        echo "FAIL $name: the traced run did not pass (log: $logs/$name.log)"
        exit 1
    fi
done
python3 -I tests/qemu/insn_profile.py "$logs/jobs-insn-y2.nm" "$logs/jobs-insn-y2.trace" \
    "$logs/jobs-insn-y4.nm" "$logs/jobs-insn-y4.trace" 2000 | sed 's/^/   /'
rm -f "$logs"/jobs-insn-y*.trace

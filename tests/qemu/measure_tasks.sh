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
#   3. Code and image bytes, from nm and size, and the deepest stack use of
#      the stackful holder (case registers), to set beside part 5's holder.
#   4. Run-to-completion jobs (the second experiment): job counts up to
#      10,000,000 (12 bytes a job; the sweep stops there by choice, and a
#      10,000,000-job build takes about 0.8 GB of host memory because the
#      queue is a Rust static), and instructions per job step, by the same
#      trace difference.
#   5. Stackless tasks (the third experiment, Rust async): task counts up to
#      what the 3 GiB can hold (the pool is reserved by the linker, so the
#      build does not grow with it), instructions per step by the same trace
#      difference, the bytes per task and the executor's deepest stack use
#      from the run logs, the code bytes, and the holder shape: the state
#      machine of a task that holds eight values across its await.
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

# image NAME CASE TASKS STACK YIELDS [JOBS [SLOT]]: build tasks-NAME.elf with the Makefile rule.
image() {
    rm -f "$out/tasks-$1.elf"
    "$make" -s --no-print-directory BUILD="$build" "TASKS_CFG_$1=$2 $3 $4 $5 ${6:-} ${7:-}" "$out/tasks-$1.elf" >/dev/null
}

# trace NAME: run tasks-NAME.elf one instruction per translation block, logging each.
trace() {
    timeout --kill-after=5 300 "$qemu" -M virt -cpu cortex-a15 -m 256M -nic none -nographic -monitor none \
        -serial stdio -semihosting-config enable=on,target=native -accel tcg,one-insn-per-tb=on \
        -d exec,nochain -D "$logs/$1.trace" -kernel "$out/tasks-$1.elf" </dev/null >"$logs/$1.log" 2>&1 || true
    "$bin/arm-none-eabi-nm" -S -C --defined-only "$out/tasks-$1.elf" >"$logs/$1.nm"
}

# deepest LOG: the deepest stack use (of a task, the runner or the executor) that a run's cost line reports.
deepest() {
    sed -n 's/^tasks: cost per .*; deepest [a-z ]*stack use \([0-9]*\) bytes$/\1/p' "$1"
}

echo "== 1. Task counts: case many, 256-byte stacks (8 + 256 = 264 bytes per task)"
echo "   QEMU seconds are host wall time for the whole run, not phone time; deepest = the"
echo "   deepest stack use in bytes that each run's log reports (stack painting)."
printf '   %-10s %7s %6s %6s %8s %8s\n' tasks yields ram result seconds deepest
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
    printf '   %-10s %7s %6s %6s %8.2f %8s\n' "$tasks" "$yields" "$ram" "$result" \
        "$(awk -v a="$start" -v b="$end" 'BEGIN { print b - a }')" "$(deepest "$logs/$name.log")"
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
    | grep -E ' (ctx_switch|task_trampoline|task_yield|yield_next|task_exited|stack_fault|tasks::(spawn|run|sched_init))$' \
    | while read -r _ size _ symbol; do printf '   %6d  %s\n' "$((16#$size))" "$symbol"; done
echo "   Image sections (size -A):"
"$bin/arm-none-eabi-size" -A -d "$out/tasks-insn-y4.elf" \
    | grep -E '^\.(text|rodata|ARM\.exidx|data|bss|stack|task_arena) ' | sed 's/^/   /'
echo "   The stackful holder (case registers: 64 tasks, each holding eight values, its seed and its"
echo "   counter across 50 yields, 256-byte stacks), for part 5's holder shape:"
image holder-stackful registers 64 256 50
if ! QEMU_TIMEOUT=60 tests/qemu/run.sh holder-stackful "$out/tasks-holder-stackful.elf" "$logs/holder-stackful.log" 0 \
    "tasks: PASS registers (64 tasks each held 8 values across 50 switches; none changed)" >/dev/null; then
    echo "FAIL holder-stackful (log: $logs/holder-stackful.log)"
    exit 1
fi
grep -h '^tasks: cost per task' "$logs/holder-stackful.log" | sed 's/^/   /'

echo "== 4. Jobs: case jobs many, one runner task (512-byte stack), 12 bytes per queued job"
printf '   %-10s %7s %6s %6s %8s %8s\n' jobs steps ram result seconds deepest
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
    printf '   %-10s %7s %6s %6s %8.2f %8s\n' "$jobs" "$steps" "$ram" "$result" \
        "$(awk -v a="$start" -v b="$end" 'BEGIN { print b - a }')" "$(deepest "$logs/$name.log")"
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

echo "== 5. Stackless tasks: case async many, one executor task (512-byte stack), 16-byte pool slots"
echo "   deepest = the executor's deepest stack use in bytes, from each run's log"
printf '   %-10s %7s %6s %6s %8s %8s\n' tasks awaits ram result seconds deepest
for spec in "1000 100 64M" "100000 10 64M" "1000000 4 256M" "10000000 2 512M" \
            "100000000 2 2048M" "200000000 2 3072M"; do
    read -r tasks steps ram <<<"$spec"
    name="async-$tasks"
    image "$name" async_many 4 512 "$steps" "$tasks" 16
    start=$(date +%s.%N)
    if QEMU_MEM=$ram QEMU_TIMEOUT=300 tests/qemu/run.sh "$name" "$out/tasks-$name.elf" "$logs/$name.log" 0 \
        "tasks: PASS async many ($tasks tasks x $steps awaits)" >/dev/null; then
        result=PASS
    else
        result=FAIL
    fi
    end=$(date +%s.%N)
    printf '   %-10s %7s %6s %6s %8.2f %8s\n' "$tasks" "$steps" "$ram" "$result" \
        "$(awk -v a="$start" -v b="$end" 'BEGIN { print b - a }')" "$(deepest "$logs/$name.log")"
    rm -f "$out/tasks-$name.elf"
done
echo "   The bytes per task, from the 1,000-task run's log:"
grep -h '^tasks: cost per async task' "$logs/async-1000.log" | sed 's/^/   /'
echo "   Per extra await (1,000 tasks, 2 and then 4 awaits each; 2,000 extra steps), by function:"
for y in 2 4; do
    name="async-insn-y$y"
    image "$name" async_many 4 512 "$y" 1000 16
    trace "$name"
    if ! grep -qF "tasks: PASS async many (1000 tasks x $y awaits)" "$logs/$name.log"; then
        echo "FAIL $name: the traced run did not pass (log: $logs/$name.log)"
        exit 1
    fi
done
python3 -I tests/qemu/insn_profile.py "$logs/async-insn-y2.nm" "$logs/async-insn-y2.trace" \
    "$logs/async-insn-y4.nm" "$logs/async-insn-y4.trace" 2000 | sed 's/^/   /'
rm -f "$logs"/async-insn-y*.trace
echo "   Executor code, by function (nm -S, the traced 4-await image):"
"$bin/arm-none-eabi-nm" -S -C --defined-only "$out/tasks-async-insn-y4.elf" \
    | grep -E ' (task_yield|yield_next|stack_fault|tasks::(executor|pool_init|async_spawn::<.*>|poll_slot::<.*>))$' \
    | while read -r _ size _ symbol; do printf '   %6d  %s\n' "$((16#$size))" "$symbol"; done
echo "   The holder shape: 64 tasks, each holding eight values, its seed and its counter across 50 awaits:"
image async-holder async_holder 4 512 50 64 48
if ! QEMU_TIMEOUT=60 tests/qemu/run.sh async-holder "$out/tasks-async-holder.elf" "$logs/async-holder.log" 0 \
    "tasks: PASS async holder (64 tasks each held 8 values across 50 awaits; none changed)" >/dev/null; then
    echo "FAIL async-holder (log: $logs/async-holder.log)"
    exit 1
fi
grep -hE '^tasks: (state machines|cost per async task|PASS)' "$logs/async-holder.log" | sed 's/^/   /'

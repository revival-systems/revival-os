//! tasks.rs - emulator-only experiment: what one task costs (ADR 0003).
//!
//! Stackful tasks with a cooperative context switch, on QEMU's `virt` board
//! (ARMv7-A, target `armv7a-none-eabi`, soft-float). A test fixture next to
//! the Phase 1 kernel (kernel.rs), not OS code: there is no `kernel/` tree yet,
//! and nothing here is a claim about the phone. Emulator timing is not phone
//! timing (docs/TESTING.md).
//!
//! Memory (ADR 0001): no heap and no allocator. One task table of fixed
//! capacity (`.bss`) and one arena of equal stack slots that the linker
//! reserves (tasks.ld), with one unused slot below them as a moat. One more
//! task costs `size_of::<Tcb>()` bytes of table plus one stack slot.
//!
//! Every limit is checked, and a failed check is reported, never undefined
//! behaviour in the scheduler:
//! - a full table refuses `spawn` with `SpawnError::TableFull`;
//! - `spawn` from a running task is refused with `SpawnError::FromTask`;
//! - every switch away from a task checks the guard word at the bottom of its
//!   stack slot, and that its stack pointer leaves room for the switch frame
//!   above that word. A failed check switches straight to the scheduler's own
//!   stack, which reports the fault and exits 1 without resuming any task;
//! - a task whose entry function returns is ended, and its slot is reclaimed.
//!
//! Limit of the guard word: it catches an overrun that writes over it. A frame
//! that skips the word without writing it is not caught, and an overrun can
//! already have written into the slot below before the next switch finds it
//! (no task is resumed after that). The MMU guard pages of ROADMAP 3b are the
//! real protection; ADR 0003 records what they cost.
//!
//! The second experiment, run-to-completion jobs on a bounded queue, is in the
//! same file: one runner task runs every job to completion on its own stack,
//! so a queued job costs a queue entry and no stack of its own.
//!
//! Configuration, set by the Makefile per image and read with `env!`:
//!   RT_TASKS   task-table capacity
//!   RT_STACK   bytes per stack slot (a multiple of 8, at least 128)
//!   RT_YIELDS  iterations per worker task (each ends with a yield), or steps
//!              per job
//!   RT_JOBS    queue capacity and jobs queued (job cases)
//!   RT_EXPECT  order checksum from tests/qemu/tasks_oracle.py (the "many"
//!              cases)
//! and one case cfg: tcase_many, tcase_full, tcase_return, tcase_registers; with
//! tgroup_overflow, tcase_overflow, tcase_overflow_sp or tcase_overflow_exit;
//! or, with tmodel_jobs, tcase_jobs_many, tcase_jobs_full, tcase_jobs_overflow.
//!
//! Calling contract: spawn and run only from the scheduler context (spawn
//! refuses a running task with SpawnError::FromTask); yield_now only from a
//! running task, and task_exited only through task_trampoline. The test cases
//! keep to this; yield_now and run do not check it themselves, so the code
//! that builds on this experiment (ROADMAP 3g) must, as spawn does.
//! The context switch is the only assembly (switch.S); kstart.S (Phase 1)
//! supplies the entry, the vectors and the semihosting exit.

#![no_std]
#![no_main]

use core::cell::UnsafeCell;
use core::hint::black_box;
use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

// ---- configuration --------------------------------------------------------

/// A decimal number from the build, checked at compile time.
const fn parse_dec(s: &str) -> usize {
    let b = s.as_bytes();
    assert!(!b.is_empty() && b.len() <= 9, "expected 1 to 9 decimal digits");
    let mut v: usize = 0;
    let mut i = 0;
    while i < b.len() {
        assert!(b[i].is_ascii_digit(), "expected a decimal number");
        v = v * 10 + (b[i] - b'0') as usize;
        i += 1;
    }
    v
}

/// A 32-bit `0x...` number from the build (lower-case), checked at compile time.
#[cfg(any(tcase_many, tcase_jobs_many))]
const fn parse_hex(s: &str) -> u32 {
    let b = s.as_bytes();
    assert!(b.len() > 2 && b.len() <= 10 && b[0] == b'0' && b[1] == b'x', "expected 0x and 1 to 8 hex digits");
    let mut v: u32 = 0;
    let mut i = 2;
    while i < b.len() {
        let d = match b[i] {
            b'0'..=b'9' => b[i] - b'0',
            b'a'..=b'f' => b[i] - b'a' + 10,
            _ => panic!("expected lower-case hex digits"),
        };
        v = (v << 4) | d as u32;
        i += 1;
    }
    v
}

const MAX_TASKS: usize = parse_dec(env!("RT_TASKS"));
const STACK_BYTES: usize = parse_dec(env!("RT_STACK"));
#[cfg(not(tcase_return))]
const YIELDS: u32 = parse_dec(env!("RT_YIELDS")) as u32;
#[cfg(any(tcase_many, tcase_jobs_many))]
const EXPECT_ORDER: u32 = parse_hex(env!("RT_EXPECT"));
#[cfg(tmodel_jobs)]
const MAX_JOBS: usize = parse_dec(env!("RT_JOBS"));

const _: () = assert!(MAX_TASKS >= 4 && MAX_TASKS < NONE as usize, "RT_TASKS out of range");
const _: () = assert!(STACK_BYTES % 8 == 0 && STACK_BYTES >= 128, "RT_STACK must be a multiple of 8, at least 128");
const _: () = assert!((MAX_TASKS + 1).checked_mul(STACK_BYTES).is_some(), "arena size overflows");
#[cfg(not(tcase_return))]
const _: () = assert!((MAX_TASKS as u64) * (YIELDS as u64) < u32::MAX as u64, "iteration total overflows");
#[cfg(tmodel_jobs)]
const _: () = assert!(MAX_JOBS >= 1 && (MAX_JOBS as u64) * (YIELDS as u64) < u32::MAX as u64, "RT_JOBS out of range");

// ---- QEMU virt hardware and the assembly this file uses -------------------

// PL011 UART0 of QEMU `virt` (as in kernel.rs).
const UART0_DR: *mut u32 = 0x0900_0000 as *mut u32;
const UART0_FR: *const u32 = 0x0900_0018 as *const u32;
const UART_FR_TXFF: u32 = 1 << 5;

extern "C" {
    /// kstart.S: Arm semihosting SYS_EXIT (the image's only `svc`).
    fn rt_exit(status: i32) -> !;
    /// switch.S: save this context's r4-r11 and lr on its stack, store sp in
    /// `*save`, load `next_sp` and resume the context saved there.
    fn ctx_switch(save: *mut usize, next_sp: usize);
    /// switch.S: first code of a new task; calls entry(arg), then task_exited.
    fn task_trampoline();
}

fn putc(b: u8) {
    // SAFETY: fixed MMIO registers of the QEMU `virt` PL011; one core.
    unsafe {
        while read_volatile(UART0_FR) & UART_FR_TXFF != 0 {}
        write_volatile(UART0_DR, b as u32);
    }
}

fn puts(s: &str) {
    for &b in s.as_bytes() {
        putc(b);
    }
}

fn put_hex(v: u32) {
    puts("0x");
    let mut shift = 28i32;
    while shift >= 0 {
        let nib = ((v >> shift) & 0xf) as u8;
        putc(if nib < 10 { b'0' + nib } else { b'a' + (nib - 10) });
        shift -= 4;
    }
}

fn put_dec(v: usize) {
    let mut buf = [0u8; 10];
    let mut n = 0usize;
    let mut u = v;
    loop {
        buf[n] = b'0' + (u % 10) as u8;
        n += 1;
        u /= 10;
        if u == 0 {
            break;
        }
    }
    while n > 0 {
        n -= 1;
        putc(buf[n]);
    }
}

// ---- the task table and the stack arena ----------------------------------

/// Shared state of a single-core, interrupts-off program.
struct Global<T>(UnsafeCell<T>);
// SAFETY: one CPU core, IRQ and FIQ masked by kstart.S, and control moves
// between tasks only through ctx_switch calls: no two accesses overlap.
unsafe impl<T> Sync for Global<T> {}
impl<T> Global<T> {
    const fn new(v: T) -> Self {
        Self(UnsafeCell::new(v))
    }
    fn ptr(&self) -> *mut T {
        self.0.get()
    }
}

/// "No task": the end of the free list, and `current` in the scheduler.
const NONE: u32 = u32::MAX;
/// The guard word at the lowest address of every stack slot.
const GUARD: u32 = 0x5354_4b47; // "GKTS" in memory order
/// Paint for the rest of each slot, to measure how deep the stack went.
const PAINT: u32 = 0xa5a5_a5a5;
/// Words in a ctx_switch frame: r4-r11 and lr (switch.S).
const FRAME_WORDS: usize = 9;
/// Room a switch needs below the yielding function's locals: the 36-byte
/// frame plus slack. A stack pointer closer than this to the guard faults.
const SWITCH_RESERVE: usize = 64;

/// One task-table entry: everything the scheduler keeps per task.
#[repr(C)]
#[derive(Clone, Copy)]
struct Tcb {
    /// The saved stack pointer while the task is not running; 0 = free slot.
    sp: usize,
    /// Ready ring: the next task to run. Free list: the next free slot.
    next: u32,
}

/// Bytes of the task arena: one unused slot (the moat) below the task slots,
/// so that an overrun of the lowest task's stack lands there and not in the
/// scheduler's own stack below it. tasks.ld reserves the region; the Makefile
/// passes this size to the linker (`--defsym=__task_arena_size=...`).
const ARENA_BYTES: usize = (MAX_TASKS + 1) * STACK_BYTES;

extern "C" {
    /// tasks.ld: the task arena, reserved, not zeroed (spawn paints each slot).
    static __task_arena_start: u8;
    static __task_arena_end: u8;
}

fn arena_start() -> usize {
    &raw const __task_arena_start as usize
}

/// The arena the linker reserved must be exactly the size this image expects.
fn arena_ok() -> bool {
    let end = &raw const __task_arena_end as usize;
    end - arena_start() == ARENA_BYTES && arena_start() % 8 == 0
}

static TCBS: Global<[Tcb; MAX_TASKS]> = Global::new([Tcb { sp: 0, next: 0 }; MAX_TASKS]);

#[derive(Clone, Copy, PartialEq, Eq)]
enum FaultKind {
    None,
    GuardWord,
    StackPointer,
}

#[derive(Clone, Copy)]
struct Fault {
    kind: FaultKind,
    task: u32,
    value: usize,
    addr: usize,
}

struct Sched {
    /// The running task, or NONE in the scheduler's own context.
    current: u32,
    /// The task before `current` in the ready ring.
    prev: u32,
    /// The last task appended to the ring (the ring is built before run()).
    tail: u32,
    /// Head of the free-slot list.
    free: u32,
    /// Tasks spawned and not yet ended.
    live: u32,
    /// Tasks whose entry function returned.
    ended: u32,
    /// The scheduler context's stack pointer while tasks run.
    main_sp: usize,
    fault: Fault,
}

static SCHED: Global<Sched> = Global::new(Sched {
    current: NONE,
    prev: NONE,
    tail: NONE,
    free: NONE,
    live: 0,
    ended: 0,
    main_sp: 0,
    fault: Fault { kind: FaultKind::None, task: NONE, value: 0, addr: 0 },
});

#[derive(Clone, Copy, PartialEq, Eq)]
enum SpawnError {
    TableFull,
    FromTask,
}

impl SpawnError {
    #[cfg_attr(tgroup_overflow, allow(dead_code))] // unused only in the overflow images
    fn name(self) -> &'static str {
        match self {
            SpawnError::TableFull => "table full",
            SpawnError::FromTask => "spawn from a running task",
        }
    }
}

/// The lowest address of a task's stack slot. Region slot 0 is the moat.
fn slot_base(slot: u32) -> usize {
    arena_start() + (slot as usize + 1) * STACK_BYTES
}

/// Puts every slot on the free list, in order (slot 0 first).
#[inline(never)] // a symbol of its own, so its size is measurable (ADR 0003)
fn sched_init() {
    // SAFETY: scheduler context, no task exists yet (see Global).
    unsafe {
        let t = TCBS.ptr();
        let mut i = 0usize;
        while i < MAX_TASKS {
            (*t)[i] = Tcb { sp: 0, next: if i + 1 < MAX_TASKS { (i + 1) as u32 } else { NONE } };
            i += 1;
        }
        (*SCHED.ptr()).free = 0;
    }
}

/// Creates a task that will run `entry(arg)` on its own stack slot, appended
/// to the ready ring. Only the scheduler context may spawn (before run()).
#[inline(never)] // a symbol of its own, so its size is measurable (ADR 0003)
fn spawn(entry: extern "C" fn(usize), arg: usize) -> Result<u32, SpawnError> {
    // SAFETY: see Global; every slot index comes from the free list, which
    // only holds indices below MAX_TASKS.
    unsafe {
        let s = SCHED.ptr();
        let t = TCBS.ptr();
        if (*s).current != NONE {
            return Err(SpawnError::FromTask);
        }
        let slot = (*s).free;
        if slot == NONE {
            return Err(SpawnError::TableFull);
        }
        (*s).free = (*t)[slot as usize].next;

        let base = slot_base(slot);
        let top = base + STACK_BYTES;
        write_volatile(base as *mut u32, GUARD);
        let mut a = base + 4;
        while a < top {
            write_volatile(a as *mut u32, PAINT);
            a += 4;
        }
        // The frame the first ctx_switch into this task pops: r4 = entry,
        // r5 = arg, r6-r11 = 0, then task_trampoline as the return address.
        let frame = top - FRAME_WORDS * 4;
        let f = frame as *mut usize;
        write_volatile(f, entry as usize);
        write_volatile(f.add(1), arg);
        let mut w = 2;
        while w < FRAME_WORDS - 1 {
            write_volatile(f.add(w), 0);
            w += 1;
        }
        write_volatile(f.add(FRAME_WORDS - 1), task_trampoline as *const () as usize);
        (*t)[slot as usize].sp = frame;

        if (*s).tail == NONE {
            (*t)[slot as usize].next = slot;
        } else {
            let tail = (*s).tail as usize;
            (*t)[slot as usize].next = (*t)[tail].next;
            (*t)[tail].next = slot;
        }
        (*s).tail = slot;
        (*s).live += 1;
        Ok(slot)
    }
}

/// Runs the ready ring, round robin, until every task has ended or a stack
/// check fails. Returns false after a fault (SCHED.fault says which).
#[inline(never)] // a symbol of its own, so its size is measurable (ADR 0003)
fn run() -> bool {
    // SAFETY: see Global.
    unsafe {
        let s = SCHED.ptr();
        let t = TCBS.ptr();
        if (*s).live == 0 {
            return true;
        }
        let head = (*t)[(*s).tail as usize].next;
        (*s).prev = (*s).tail;
        (*s).current = head;
        ctx_switch(&raw mut (*s).main_sp, (*t)[head as usize].sp);
        // Back on the scheduler's stack: the last task ended, or a fault.
        (*s).current = NONE;
        (*s).tail = NONE;
        (*s).fault.kind == FaultKind::None
    }
}

/// Checks the running task's stack before control leaves it. On failure it
/// does not return: the scheduler reports the fault and resumes no task.
#[inline(always)]
fn check_stack(cur: u32) {
    let base = slot_base(cur);
    // SAFETY: base is the start of the running task's slot in ARENA.
    let guard = unsafe { read_volatile(base as *const u32) };
    if guard != GUARD {
        fault(cur, FaultKind::GuardWord, guard as usize, base);
    }
    let probe = 0u32;
    let sp = black_box(&probe) as *const u32 as usize;
    if sp < base + 4 + SWITCH_RESERVE {
        fault(cur, FaultKind::StackPointer, sp, base);
    }
}

/// Leaves a task whose stack check failed: records the fault and switches to
/// the scheduler's stack for good.
#[cold]
#[inline(never)]
fn fault(cur: u32, kind: FaultKind, value: usize, addr: usize) -> ! {
    // SAFETY: see Global. main_sp holds the scheduler context saved by run().
    unsafe {
        let s = SCHED.ptr();
        (*s).fault = Fault { kind, task: cur, value, addr };
        let mut dead: usize = 0;
        ctx_switch(&raw mut dead, (*s).main_sp);
        rt_exit(3) // not reached: run() never resumes a faulted task
    }
}

/// Gives the CPU to the next task in the ring (round robin). Only a running
/// task may call it (the calling contract in the header).
#[inline(never)]
fn yield_now() {
    // SAFETY: see Global. Called from a running task, so `current` is a live
    // task below MAX_TASKS, and every ring index is below MAX_TASKS.
    unsafe {
        let s = SCHED.ptr();
        let t = TCBS.ptr();
        let cur = (*s).current;
        check_stack(cur);
        let next = (*t)[cur as usize].next;
        if next == cur {
            return;
        }
        (*s).prev = cur;
        (*s).current = next;
        ctx_switch(&raw mut (*t)[cur as usize].sp, (*t)[next as usize].sp);
    }
}

/// Called by task_trampoline when a task's entry function returns: ends the
/// task, frees its slot and switches to the next task, or to the scheduler
/// after the last one. Runs on the ended task's stack until that switch; no
/// spawn can claim the slot first, because spawn is refused while tasks run.
#[no_mangle]
pub extern "C" fn task_exited() -> ! {
    // SAFETY: see Global.
    unsafe {
        let s = SCHED.ptr();
        let t = TCBS.ptr();
        let cur = (*s).current;
        check_stack(cur);
        let next = (*t)[cur as usize].next;
        let prev = (*s).prev;
        (*t)[cur as usize] = Tcb { sp: 0, next: (*s).free };
        (*s).free = cur;
        (*s).live -= 1;
        (*s).ended += 1;
        let mut dead: usize = 0;
        if (*s).live == 0 {
            (*s).current = NONE;
            ctx_switch(&raw mut dead, (*s).main_sp);
        } else {
            (*t)[prev as usize].next = next;
            (*s).current = next;
            ctx_switch(&raw mut dead, (*t)[next as usize].sp);
        }
        rt_exit(3) // not reached: an ended task is never resumed
    }
}

/// Bytes of a slot written since its spawn (painted words overwritten),
/// counted down from the top. Valid until the slot is spawned again.
#[cfg_attr(tgroup_overflow, allow(dead_code))] // unused only in the overflow images
fn high_water(slot: u32) -> usize {
    let base = slot_base(slot);
    let top = base + STACK_BYTES;
    let mut a = base + 4;
    // SAFETY: reads inside the slot.
    while a < top && unsafe { read_volatile(a as *const u32) } == PAINT {
        a += 4;
    }
    top - a
}

#[cfg_attr(any(tgroup_overflow, tmodel_jobs), allow(dead_code))] // unused in the overflow and job images
fn max_high_water(slots: usize) -> usize {
    let mut max = 0;
    let mut i = 0;
    while i < slots {
        let h = high_water(i as u32);
        if h > max {
            max = h;
        }
        i += 1;
    }
    max
}

/// Free slots, counted along the free list (bounded, in case it is corrupt).
#[cfg_attr(any(tgroup_overflow, tcase_jobs_overflow), allow(dead_code))] // unused in the overflow images
fn free_count() -> usize {
    // SAFETY: see Global.
    unsafe {
        let t = TCBS.ptr();
        let mut n = 0usize;
        let mut i = (*SCHED.ptr()).free;
        while i != NONE && n <= MAX_TASKS {
            n += 1;
            i = (*t)[i as usize].next;
        }
        n
    }
}

fn report_fault() {
    // SAFETY: scheduler context after run() returned.
    let f = unsafe { (*SCHED.ptr()).fault };
    puts("tasks: FAULT stack overflow in task ");
    put_dec(f.task as usize);
    match f.kind {
        FaultKind::GuardWord => {
            puts(": guard word at ");
            put_hex(f.addr as u32);
            puts(" reads ");
            put_hex(f.value as u32);
            puts(", not ");
            put_hex(GUARD);
        }
        FaultKind::StackPointer => {
            puts(": stack pointer ");
            put_hex(f.value as u32);
            puts(" leaves no room for a switch above the guard word at ");
            put_hex(f.addr as u32);
        }
        FaultKind::None => puts(": (no fault recorded)"),
    }
    puts("; found at a switch, no task resumed\n");
}

#[cfg_attr(any(tgroup_overflow, tmodel_jobs), allow(dead_code))] // unused in the overflow and job images
fn report_cost(slots: usize) {
    puts("tasks: cost per task: ");
    put_dec(core::mem::size_of::<Tcb>());
    puts(" bytes of table + ");
    put_dec(STACK_BYTES);
    puts(" bytes of stack = ");
    put_dec(core::mem::size_of::<Tcb>() + STACK_BYTES);
    puts(" bytes; deepest stack use ");
    put_dec(max_high_water(slots));
    puts(" bytes\n");
}

fn header(case: &str) {
    puts("tasks: case ");
    puts(case);
    puts(", capacity ");
    put_dec(MAX_TASKS);
    puts(", ");
    put_dec(STACK_BYTES);
    puts("-byte stacks, table ");
    put_dec(core::mem::size_of::<[Tcb; MAX_TASKS]>());
    puts(" bytes, arena ");
    put_dec(ARENA_BYTES);
    puts(" bytes (one slot of it the moat)\n");
}

// ---- the test cases ---------------------------------------------------------

/// Counters the worker tasks update (test bookkeeping, not per-task cost).
struct Stats {
    /// Iterations run, over all tasks.
    total: u32,
    /// Order checksum: depends on which task ran each iteration, in order
    /// (an FNV-1a style step: xor, then multiply by an odd constant).
    #[cfg(any(tcase_many, tmodel_jobs))]
    order: u32,
    /// Case "return": the spawn attempted from a running task was refused.
    #[cfg(tcase_return)]
    probe_refused: bool,
}

static STATS: Global<Stats> = Global::new(Stats {
    total: 0,
    #[cfg(any(tcase_many, tmodel_jobs))]
    order: 0x1234_5678,
    #[cfg(tcase_return)]
    probe_refused: false,
});

/// One iteration of bookkeeping, then a yield. tests/qemu/tasks_oracle.py
/// computes the same order checksum for N tasks run round robin.
#[cfg(any(tcase_many, tcase_full, tgroup_overflow))]
extern "C" fn worker(arg: usize) {
    #[cfg_attr(not(tcase_many), allow(unused_variables))]
    let id = arg as u32;
    let mut i = 0u32;
    while i < YIELDS {
        // SAFETY: see Global.
        unsafe {
            let st = STATS.ptr();
            (*st).total += 1;
            #[cfg(tcase_many)]
            {
                (*st).order = ((*st).order ^ id.wrapping_mul(0x9e37_79b9).wrapping_add(i)).wrapping_mul(0x0100_0193);
            }
        }
        i += 1;
        yield_now();
    }
}

#[cfg(any(tcase_many, tcase_full))]
fn spawn_workers(n: usize) -> bool {
    let mut i = 0;
    while i < n {
        if let Err(e) = spawn(worker, i) {
            puts("tasks: FAIL spawn of task ");
            put_dec(i);
            puts(" refused: ");
            puts(e.name());
            putc(b'\n');
            return false;
        }
        i += 1;
    }
    true
}

/// MAX_TASKS tasks, YIELDS iterations each: the totals and the round-robin
/// order must be exactly the expected ones.
#[cfg(tcase_many)]
fn case() -> i32 {
    header("many");
    if !spawn_workers(MAX_TASKS) {
        return 1;
    }
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let (total, order, ended, live) = unsafe {
        let st = STATS.ptr();
        let s = SCHED.ptr();
        ((*st).total, (*st).order, (*s).ended, (*s).live)
    };
    let want = MAX_TASKS as u32 * YIELDS;
    puts("tasks: total ");
    put_dec(total as usize);
    puts(" (want ");
    put_dec(want as usize);
    puts("), order ");
    put_hex(order);
    puts(" (want ");
    put_hex(EXPECT_ORDER);
    puts("), ended ");
    put_dec(ended as usize);
    puts(", live ");
    put_dec(live as usize);
    putc(b'\n');
    report_cost(MAX_TASKS);
    if total == want && order == EXPECT_ORDER && ended as usize == MAX_TASKS && live == 0 && free_count() == MAX_TASKS {
        puts("tasks: PASS many (");
        put_dec(MAX_TASKS);
        puts(" tasks x ");
        put_dec(YIELDS as usize);
        puts(" yields)\n");
        0
    } else {
        puts("tasks: FAIL many\n");
        1
    }
}

/// A full table refuses one more spawn, and the refusal changes nothing: the
/// tasks already in it run to the expected total.
#[cfg(tcase_full)]
fn case() -> i32 {
    header("full");
    if !spawn_workers(MAX_TASKS) {
        return 1;
    }
    match spawn(worker, MAX_TASKS) {
        Err(SpawnError::TableFull) => {
            puts("tasks: spawn ");
            put_dec(MAX_TASKS + 1);
            puts(" refused: table full (");
            put_dec(MAX_TASKS);
            puts(" of ");
            put_dec(MAX_TASKS);
            puts(")\n");
        }
        Err(e) => {
            puts("tasks: FAIL spawn beyond capacity refused for the wrong reason: ");
            puts(e.name());
            putc(b'\n');
            return 1;
        }
        Ok(slot) => {
            puts("tasks: FAIL spawn beyond capacity accepted, slot ");
            put_dec(slot as usize);
            putc(b'\n');
            return 1;
        }
    }
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let (total, ended) = unsafe { ((*STATS.ptr()).total, (*SCHED.ptr()).ended) };
    let want = MAX_TASKS as u32 * YIELDS;
    report_cost(MAX_TASKS);
    if total == want && ended as usize == MAX_TASKS && free_count() == MAX_TASKS {
        puts("tasks: PASS full (spawn ");
        put_dec(MAX_TASKS + 1);
        puts(" of ");
        put_dec(MAX_TASKS);
        puts(" refused; the ");
        put_dec(MAX_TASKS);
        puts(" tasks then ran ");
        put_dec(total as usize);
        puts(" iterations)\n");
        0
    } else {
        puts("tasks: FAIL full: total ");
        put_dec(total as usize);
        puts(", want ");
        put_dec(want as usize);
        putc(b'\n');
        1
    }
}

/// Writes STACK_BYTES bytes of locals: more than the slot has left, so the
/// writes run over the guard word into the slot below.
#[cfg(any(tcase_overflow, tcase_overflow_exit, tcase_jobs_overflow))]
#[inline(never)]
fn smash_stack() {
    let mut buf = [0u32; STACK_BYTES / 4];
    let p = black_box(&mut buf) as *mut [u32; STACK_BYTES / 4] as *mut u32;
    let mut i = 0;
    while i < STACK_BYTES / 4 {
        // SAFETY: inside `buf`; that `buf` itself overruns the slot is the
        // point of this negative test.
        unsafe { write_volatile(p.add(i), 0x0bad_57ac) };
        i += 1;
    }
    black_box(&buf);
}

#[cfg(tcase_overflow)]
extern "C" fn overflower(_arg: usize) {
    yield_now();
    smash_stack();
    yield_now(); // the check in this switch must stop the task
    puts("tasks: FAIL overflow not detected; the task kept running\n");
    // SAFETY: semihosting exit.
    unsafe { rt_exit(1) }
}

/// Yields from inside a frame that leaves less room than a switch needs above
/// the guard word, without writing it: only the stack-pointer check can see it.
#[cfg(tcase_overflow_sp)]
#[inline(never)]
fn yield_from_deep_frame() {
    let deep = core::mem::MaybeUninit::<[u32; (STACK_BYTES - 96) / 4]>::uninit();
    black_box(&deep);
    yield_now(); // the stack-pointer check in this switch must stop the task
    black_box(&deep);
}

#[cfg(tcase_overflow_sp)]
extern "C" fn deep_yielder(_arg: usize) {
    yield_now();
    yield_from_deep_frame();
    puts("tasks: FAIL the deep yield was not stopped\n");
    // SAFETY: semihosting exit.
    unsafe { rt_exit(1) }
}

/// Overruns its stack and returns without yielding: only the check at the
/// task's exit can see it.
#[cfg(tcase_overflow_exit)]
extern "C" fn smash_and_return(_arg: usize) {
    yield_now();
    smash_stack();
}

/// Task 1 of 3 (tasks 0 and 2 are workers) misuses its stack. The fault must
/// be the expected kind, in task 1, found at its next switch: after exactly 3
/// iterations (two of task 0, one of task 2), with no task resumed after it.
#[cfg(tgroup_overflow)]
fn overflow_case(case: &str, culprit: extern "C" fn(usize), want: FaultKind, found_by: &str) -> i32 {
    header(case);
    if spawn(worker, 0).is_err() || spawn(culprit, 1).is_err() || spawn(worker, 2).is_err() {
        puts("tasks: FAIL spawn\n");
        return 1;
    }
    if run() {
        puts("tasks: FAIL ");
        puts(case);
        puts(": the run ended without a fault\n");
        return 1;
    }
    report_fault();
    // SAFETY: scheduler context after run().
    let (total, f) = unsafe { ((*STATS.ptr()).total, (*SCHED.ptr()).fault) };
    puts("tasks: iterations run before the fault: ");
    put_dec(total as usize);
    putc(b'\n');
    if f.kind == want && f.task == 1 && total == 3 {
        puts("tasks: FAULT found by ");
        puts(found_by);
        puts(" (task 1, 3 iterations before it); no task resumed\n");
    }
    1
}

#[cfg(tcase_overflow)]
fn case() -> i32 {
    overflow_case("overflow", overflower, FaultKind::GuardWord, "the guard-word check at the task's next yield")
}

#[cfg(tcase_overflow_sp)]
fn case() -> i32 {
    overflow_case("overflow, stack pointer", deep_yielder, FaultKind::StackPointer, "the stack-pointer check at the task's yield")
}

#[cfg(tcase_overflow_exit)]
fn case() -> i32 {
    overflow_case("overflow at exit", smash_and_return, FaultKind::GuardWord, "the guard-word check at the task's exit")
}

/// Task k yields k % 4 times, then returns (k % 4 == 0 returns at once).
#[cfg(tcase_return)]
extern "C" fn short_lived(arg: usize) {
    let mut i = 0;
    while i < arg % 4 {
        // SAFETY: see Global.
        unsafe { (*STATS.ptr()).total += 1 };
        i += 1;
        yield_now();
    }
}

/// Tries to spawn from inside a running task, after task 0 has returned and
/// freed slot 0: the spawn must be refused.
#[cfg(tcase_return)]
extern "C" fn spawn_prober(_arg: usize) {
    yield_now();
    let refused = spawn(short_lived, 0) == Err(SpawnError::FromTask);
    // SAFETY: see Global.
    unsafe { (*STATS.ptr()).probe_refused = refused };
}

/// Iterations short_lived tasks 0..n run in total.
#[cfg(tcase_return)]
fn short_lived_total(n: usize) -> u32 {
    let mut sum = 0;
    let mut k = 0;
    while k < n {
        sum += (k % 4) as u32;
        k += 1;
    }
    sum
}

/// Tasks that return are ended and their slots reclaimed: a second wave fills
/// every slot again.
#[cfg(tcase_return)]
fn case() -> i32 {
    header("return");
    // Wave 1: MAX_TASKS - 1 short-lived tasks and the spawn prober.
    let mut k = 0;
    while k < MAX_TASKS - 1 {
        if spawn(short_lived, k).is_err() {
            puts("tasks: FAIL wave 1 spawn\n");
            return 1;
        }
        k += 1;
    }
    if spawn(spawn_prober, 0).is_err() {
        puts("tasks: FAIL wave 1 spawn\n");
        return 1;
    }
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let (ended1, live1, total1, refused) =
        unsafe { ((*SCHED.ptr()).ended, (*SCHED.ptr()).live, (*STATS.ptr()).total, (*STATS.ptr()).probe_refused) };
    let free1 = free_count();
    puts("tasks: wave 1: ended ");
    put_dec(ended1 as usize);
    puts(", live ");
    put_dec(live1 as usize);
    puts(", free slots ");
    put_dec(free1);
    puts(", iterations ");
    put_dec(total1 as usize);
    puts(if refused { ", spawn from a running task refused\n" } else { ", spawn from a running task NOT refused\n" });
    report_cost(MAX_TASKS);
    if ended1 as usize != MAX_TASKS || live1 != 0 || free1 != MAX_TASKS || total1 != short_lived_total(MAX_TASKS - 1) || !refused {
        puts("tasks: FAIL return (wave 1)\n");
        return 1;
    }
    // Wave 2: every slot again.
    k = 0;
    while k < MAX_TASKS {
        if let Err(e) = spawn(short_lived, k) {
            puts("tasks: FAIL wave 2 spawn ");
            put_dec(k);
            puts(" refused: ");
            puts(e.name());
            puts("; a slot was not reclaimed\n");
            return 1;
        }
        k += 1;
    }
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let (ended2, live2) = unsafe { ((*SCHED.ptr()).ended, (*SCHED.ptr()).live) };
    let free2 = free_count();
    if ended2 as usize == 2 * MAX_TASKS && live2 == 0 && free2 == MAX_TASKS {
        puts("tasks: PASS return (wave 1: ");
        put_dec(MAX_TASKS);
        puts(" tasks returned and ");
        put_dec(free1);
        puts(" slots reclaimed; spawn from a running task refused; wave 2: ");
        put_dec(MAX_TASKS);
        puts(" tasks in the same slots returned)\n");
        0
    } else {
        puts("tasks: FAIL return (wave 2): ended ");
        put_dec(ended2 as usize);
        puts(", free slots ");
        put_dec(free2);
        putc(b'\n');
        1
    }
}

/// Holds eight opaque values, its seed and its counter across every yield:
/// more live values than there are free callee-saved registers, so the
/// compiler keeps them in r4-r11 (and the stack) across ctx_switch. After
/// each yield every value must be unchanged; a switch that stopped saving
/// any of r4-r11 corrupts one of them.
#[cfg(tcase_registers)]
extern "C" fn holder(arg: usize) {
    let seed = arg as u32;
    let a = black_box(seed ^ 0x1111_1111);
    let b = black_box(seed ^ 0x2222_2222);
    let c = black_box(seed ^ 0x3333_3333);
    let d = black_box(seed ^ 0x4444_4444);
    let e = black_box(seed ^ 0x5555_5555);
    let f = black_box(seed ^ 0x6666_6666);
    let g = black_box(seed ^ 0x7777_7777);
    let h = black_box(seed ^ 0x0888_8888);
    let mut i = 0u32;
    while i < YIELDS {
        yield_now();
        let ok = a == seed ^ 0x1111_1111
            && b == seed ^ 0x2222_2222
            && c == seed ^ 0x3333_3333
            && d == seed ^ 0x4444_4444
            && e == seed ^ 0x5555_5555
            && f == seed ^ 0x6666_6666
            && g == seed ^ 0x7777_7777
            && h == seed ^ 0x0888_8888;
        if !ok {
            puts("tasks: FAIL registers: a value held across a switch changed in task ");
            put_dec(seed as usize);
            putc(b'\n');
            // SAFETY: semihosting exit.
            unsafe { rt_exit(1) }
        }
        // SAFETY: see Global.
        unsafe { (*STATS.ptr()).total += 1 };
        i = black_box(i + 1);
    }
}

/// MAX_TASKS holders interleaved: every value survives every switch.
#[cfg(tcase_registers)]
fn case() -> i32 {
    header("registers");
    let mut k = 0;
    while k < MAX_TASKS {
        if let Err(err) = spawn(holder, k) {
            puts("tasks: FAIL spawn refused: ");
            puts(err.name());
            putc(b'\n');
            return 1;
        }
        k += 1;
    }
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let total = unsafe { (*STATS.ptr()).total };
    report_cost(MAX_TASKS);
    if total == MAX_TASKS as u32 * YIELDS && free_count() == MAX_TASKS {
        puts("tasks: PASS registers (");
        put_dec(MAX_TASKS);
        puts(" tasks each held 8 values across ");
        put_dec(YIELDS as usize);
        puts(" switches; none changed)\n");
        0
    } else {
        puts("tasks: FAIL registers: total ");
        put_dec(total as usize);
        putc(b'\n');
        1
    }
}

// ---- the second experiment: run-to-completion jobs on a bounded queue -------

/// One queued job: the step to run and its state. A step returns true to run
/// again (the job is queued again at the tail) or false when the job is done.
/// `None` only in free queue entries.
#[cfg(tmodel_jobs)]
#[derive(Clone, Copy)]
struct Job {
    step: Option<fn(u32, u32) -> bool>,
    id: u32,
    iter: u32,
}

/// A ring buffer of MAX_JOBS jobs (`.bss`): a queued job costs one entry.
#[cfg(tmodel_jobs)]
struct Queue {
    jobs: [Job; MAX_JOBS],
    head: usize,
    len: usize,
}

#[cfg(tmodel_jobs)]
static QUEUE: Global<Queue> =
    Global::new(Queue { jobs: [Job { step: None, id: 0, iter: 0 }; MAX_JOBS], head: 0, len: 0 });

/// Queues a job at the tail; a full queue refuses it.
#[cfg(tmodel_jobs)]
fn push(job: Job) -> Result<(), ()> {
    // SAFETY: see Global.
    unsafe {
        let q = QUEUE.ptr();
        if (*q).len == MAX_JOBS {
            return Err(());
        }
        let mut tail = (*q).head + (*q).len;
        if tail >= MAX_JOBS {
            tail -= MAX_JOBS;
        }
        (*q).jobs[tail] = job;
        (*q).len += 1;
        Ok(())
    }
}

/// Takes the job at the head, if any.
#[cfg(tmodel_jobs)]
fn pop() -> Option<Job> {
    // SAFETY: see Global.
    unsafe {
        let q = QUEUE.ptr();
        if (*q).len == 0 {
            return None;
        }
        let job = (*q).jobs[(*q).head];
        (*q).head += 1;
        if (*q).head == MAX_JOBS {
            (*q).head = 0;
        }
        (*q).len -= 1;
        Some(job)
    }
}

#[cfg(tmodel_jobs)]
fn queued() -> usize {
    // SAFETY: see Global.
    unsafe { (*QUEUE.ptr()).len }
}

/// The job runner: one task, one stack, every job. Runs each step to
/// completion, then yields (it is the only task here, so the yield checks its
/// stack and returns: a job that overran the stack is reported from the
/// scheduler's stack), then queues the job again at the tail if it is not done.
#[cfg(tmodel_jobs)]
extern "C" fn job_runner(_arg: usize) {
    while let Some(job) = pop() {
        let Some(step) = job.step else {
            puts("tasks: FAIL a queued job has no step\n");
            // SAFETY: semihosting exit.
            unsafe { rt_exit(1) }
        };
        let again = step(job.id, job.iter);
        yield_now();
        // pop() freed an entry, so this push cannot be refused.
        if again && push(Job { step: job.step, id: job.id, iter: job.iter + 1 }).is_err() {
            puts("tasks: FAIL a job could not be queued again\n");
            // SAFETY: semihosting exit.
            unsafe { rt_exit(1) }
        }
    }
}

/// One step of job `id`: the same bookkeeping as one iteration of a worker
/// task, so the order checksum of N jobs equals that of N tasks.
#[cfg(tmodel_jobs)]
fn count_step(id: u32, iter: u32) -> bool {
    // SAFETY: see Global.
    unsafe {
        let st = STATS.ptr();
        (*st).total += 1;
        (*st).order = ((*st).order ^ id.wrapping_mul(0x9e37_79b9).wrapping_add(iter)).wrapping_mul(0x0100_0193);
    }
    iter + 1 < YIELDS
}

/// Queues `n` jobs of `step`, ids 0..n.
#[cfg(any(tcase_jobs_many, tcase_jobs_full))]
fn queue_jobs(n: usize, step: fn(u32, u32) -> bool) -> bool {
    let mut i = 0;
    while i < n {
        if push(Job { step: Some(step), id: i as u32, iter: 0 }).is_err() {
            puts("tasks: FAIL queueing job ");
            put_dec(i);
            puts(": queue full\n");
            return false;
        }
        i += 1;
    }
    true
}

/// Spawns the one runner task.
#[cfg(tmodel_jobs)]
fn spawn_runner() -> bool {
    if let Err(e) = spawn(job_runner, 0) {
        puts("tasks: FAIL spawn of the runner refused: ");
        puts(e.name());
        putc(b'\n');
        return false;
    }
    true
}

#[cfg(tmodel_jobs)]
fn jobs_header(case: &str) {
    header(case);
    puts("tasks: jobs ");
    put_dec(MAX_JOBS);
    puts(", queue ");
    put_dec(core::mem::size_of::<[Job; MAX_JOBS]>());
    puts(" bytes\n");
}

#[cfg(tmodel_jobs)]
fn report_job_cost() {
    puts("tasks: cost per queued job: ");
    put_dec(core::mem::size_of::<Job>());
    puts(" bytes; one runner task for all of them: ");
    put_dec(core::mem::size_of::<Tcb>() + STACK_BYTES);
    puts(" bytes; deepest runner stack use ");
    put_dec(high_water(0));
    puts(" bytes\n");
}

/// MAX_JOBS jobs of YIELDS steps each, run to completion one step at a time
/// in FIFO order: the totals and the order must be exactly the expected ones.
#[cfg(tcase_jobs_many)]
fn case() -> i32 {
    jobs_header("jobs many");
    if !queue_jobs(MAX_JOBS, count_step) || !spawn_runner() {
        return 1;
    }
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let (total, order, ended) = unsafe { ((*STATS.ptr()).total, (*STATS.ptr()).order, (*SCHED.ptr()).ended) };
    let want = MAX_JOBS as u32 * YIELDS;
    puts("tasks: total ");
    put_dec(total as usize);
    puts(" (want ");
    put_dec(want as usize);
    puts("), order ");
    put_hex(order);
    puts(" (want ");
    put_hex(EXPECT_ORDER);
    puts("), jobs left ");
    put_dec(queued());
    putc(b'\n');
    report_job_cost();
    if total == want && order == EXPECT_ORDER && queued() == 0 && ended == 1 && free_count() == MAX_TASKS {
        puts("tasks: PASS jobs many (");
        put_dec(MAX_JOBS);
        puts(" jobs x ");
        put_dec(YIELDS as usize);
        puts(" steps)\n");
        0
    } else {
        puts("tasks: FAIL jobs many\n");
        1
    }
}

/// A full queue refuses one more job, and the refusal changes nothing: the
/// queued jobs run to the expected total.
#[cfg(tcase_jobs_full)]
fn case() -> i32 {
    jobs_header("jobs full");
    if !queue_jobs(MAX_JOBS, count_step) || !spawn_runner() {
        return 1;
    }
    if push(Job { step: Some(count_step), id: MAX_JOBS as u32, iter: 0 }).is_ok() {
        puts("tasks: FAIL a job beyond the queue's capacity was accepted\n");
        return 1;
    }
    puts("tasks: job ");
    put_dec(MAX_JOBS + 1);
    puts(" refused: queue full (");
    put_dec(MAX_JOBS);
    puts(" of ");
    put_dec(MAX_JOBS);
    puts(")\n");
    if !run() {
        report_fault();
        return 1;
    }
    // SAFETY: scheduler context after run().
    let (total, order) = unsafe { ((*STATS.ptr()).total, (*STATS.ptr()).order) };
    let want = MAX_JOBS as u32 * YIELDS;
    report_job_cost();
    if total == want && queued() == 0 && free_count() == MAX_TASKS {
        puts("tasks: PASS jobs full (job ");
        put_dec(MAX_JOBS + 1);
        puts(" of ");
        put_dec(MAX_JOBS);
        puts(" refused; the ");
        put_dec(MAX_JOBS);
        puts(" jobs then ran ");
        put_dec(total as usize);
        puts(" steps, order ");
        put_hex(order);
        puts(")\n");
        0
    } else {
        puts("tasks: FAIL jobs full: total ");
        put_dec(total as usize);
        puts(", want ");
        put_dec(want as usize);
        putc(b'\n');
        1
    }
}

/// A job step that overruns the runner's stack.
#[cfg(tcase_jobs_overflow)]
fn smash_step(_id: u32, _iter: u32) -> bool {
    smash_stack();
    false
}

/// Job 1 of 3 overruns the runner's stack; the check after its step must
/// report it.
#[cfg(tcase_jobs_overflow)]
fn case() -> i32 {
    jobs_header("jobs overflow");
    let queued_ok = push(Job { step: Some(count_step), id: 0, iter: 0 }).is_ok()
        && push(Job { step: Some(smash_step), id: 1, iter: 0 }).is_ok()
        && push(Job { step: Some(count_step), id: 2, iter: 0 }).is_ok();
    if !queued_ok {
        puts("tasks: FAIL queueing\n");
        return 1;
    }
    if !spawn_runner() {
        return 1;
    }
    if run() {
        puts("tasks: FAIL jobs overflow: the run ended without a fault\n");
        return 1;
    }
    report_fault();
    // SAFETY: scheduler context after run().
    let (total, order) = unsafe { ((*STATS.ptr()).total, (*STATS.ptr()).order) };
    puts("tasks: steps run before the fault: ");
    put_dec(total as usize);
    puts(", order ");
    put_hex(order);
    puts(", jobs left ");
    put_dec(queued());
    putc(b'\n');
    report_job_cost();
    // The runner checks its stack after every step, so the fault must come
    // after job 1's step and before job 2's: one step ran (job 0's), and job 2
    // is still queued. A check only at the runner's exit would let job 2 run.
    // SAFETY: scheduler context after run().
    let f = unsafe { (*SCHED.ptr()).fault };
    if f.kind == FaultKind::GuardWord && f.task == 0 && total == 1 && queued() == 1 {
        puts("tasks: FAULT found after the overrunning job's step, before the next job ran\n");
    }
    1
}

// ---- entry, exceptions, panic ---------------------------------------------

/// Called by kstart.S after the stack and .bss are set up; returns the exit
/// status for the semihosting exit.
#[no_mangle]
pub extern "C" fn kmain() -> i32 {
    if !arena_ok() {
        puts("tasks: FAIL the linker's task arena is not the ");
        put_dec(ARENA_BYTES);
        puts(" bytes this image expects\n");
        return 1;
    }
    sched_init();
    case()
}

/// Called from the kstart.S vector stubs (on the scheduler's stack).
#[no_mangle]
pub extern "C" fn kexception(vector: u32) -> ! {
    puts("tasks: unexpected exception, vector ");
    put_dec(vector as usize);
    putc(b'\n');
    // SAFETY: semihosting exit.
    unsafe { rt_exit(1) }
}

#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    puts("panic: ");
    if let Some(loc) = info.location() {
        puts(loc.file());
        putc(b':');
        put_dec(loc.line() as usize);
    }
    putc(b'\n');
    // SAFETY: semihosting exit.
    unsafe { rt_exit(1) }
}

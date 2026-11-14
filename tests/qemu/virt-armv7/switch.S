/*
 * switch.S - the cooperative context switch and the stack checks of the
 * emulator-only task experiment (tasks.rs, ADR 0003). QEMU `virt` test
 * fixture, not OS code.
 *
 * Why this cannot be Rust (ADR 0001):
 * - ctx_switch saves the callee-saved registers r4-r11 and the return
 *   address of one call chain, stores its stack pointer, loads another and
 *   resumes the other chain. Rust can neither name those registers nor
 *   replace the stack pointer under its own code.
 * - task_yield, and the end of task_trampoline, check the running task's
 *   stack before anything is written to it: the guard word at the bottom of
 *   its slot, and the stack pointer itself. Rust cannot read sp (round 1 used
 *   the address of a local as a stand-in), and every Rust function may push
 *   in its prologue. A failed check leaves for the scheduler's stack without
 *   writing to the failed one; round 1's Rust fault path wrote 52 bytes on it
 *   (ADR 0003, round 2).
 * - task_trampoline starts a new task from the frame spawn() built: the
 *   entry function in r4 and its argument in r5.
 * Everything else (choosing the next task, the task table, reporting) is Rust.
 *
 * Calling convention (AAPCS, soft-float): r0-r3, r12 and lr are caller-saved,
 * so a call to ctx_switch only has to preserve r4-r11 and sp, and the checks
 * may use r0-r3 and r12 freely. There is no VFP state (Makefile ARM_ARCH).
 * Interrupts stay masked (kstart.S), so nothing runs between the steps.
 *
 * TASK_CHECK (tasks.rs, #[repr(C)]; the offsets are asserted there):
 *    0 base     the running task's slot base, the address of its guard word
 *    4 guard    the guard value
 *    8 reserve  the bytes a switch needs above the guard word
 *   12 main_sp  the scheduler context's saved stack pointer (run())
 *   16 kind     written on a failure: 1 guard word, 2 stack pointer
 *   20 value    the guard word read, or the stack pointer
 *   24 addr     the guard word's address
 */
    .syntax unified
    .arm

    .equ    TC_BASE, 0
    .equ    TC_GUARD, 4
    .equ    TC_RESERVE, 8
    .equ    TC_MAIN_SP, 12
    .equ    TC_KIND, 16
    .equ    TC_VALUE, 20
    .equ    TC_ADDR, 24

/*
 * ctx_switch(save: *mut usize, next_sp: usize)
 *   Pushes r4-r11 and lr on the current stack, stores that sp in *save, loads
 *   next_sp, and pops the next context's r4-r11 and pc. The next context
 *   resumes where it called ctx_switch, or, for a new task, in
 *   task_trampoline (the initial frame built by tasks.rs spawn()).
 *   Frame: 9 words, r4 at the lowest address, the saved lr at the highest.
 */
    .section .text.ctx_switch, "ax"
    .global ctx_switch
    .type   ctx_switch, %function
ctx_switch:
    push    {r4-r11, lr}
    str     sp, [r0]
    mov     sp, r1
    pop     {r4-r11, pc}
    .size   ctx_switch, . - ctx_switch

/*
 * The two checks, on the running task's stack as it is: the guard word must
 * be intact, and sp must leave `reserve` bytes above it. Uses r0-r2 and r12
 * only, writes nothing, falls through when both pass and branches to
 * stack_fault_guard or stack_fault_sp otherwise, with r0 = the slot base and
 * r12 = TASK_CHECK.
 */
    .macro  check_stack
    ldr     r12, =TASK_CHECK
    ldr     r0, [r12, #TC_BASE]
    ldr     r1, [r0]
    ldr     r2, [r12, #TC_GUARD]
    cmp     r1, r2
    bne     stack_fault_guard
    ldr     r2, [r12, #TC_RESERVE]
    add     r2, r0, r2
    add     r2, r2, #4
    cmp     sp, r2
    blo     stack_fault_sp
    .endm

/*
 * task_yield(): the checks, then the Rust half of the yield (yield_next) by a
 * tail branch, so that yield_next returns straight to task_yield's caller.
 */
    .section .text.task_yield, "ax"
    .global task_yield
    .type   task_yield, %function
task_yield:
    check_stack
    b       yield_next
    .size   task_yield, . - task_yield

/*
 * task_trampoline: the first code a new task runs. spawn() leaves the task's
 * entry function in r4 and its argument in r5 (initial frame), and this
 * address as the frame's saved lr. When the entry function returns, the
 * checks run before task_exited (Rust, never returns) can push anything.
 */
    .section .text.task_trampoline, "ax"
    .global task_trampoline
    .type   task_trampoline, %function
task_trampoline:
    mov     r0, r5
    blx     r4
    check_stack
    b       task_exited
    .size   task_trampoline, . - task_trampoline

/*
 * A failed check: record it in TASK_CHECK and resume the scheduler's context
 * saved by run(), without writing to the failed stack: no push, no call.
 * run() then finds TASK_CHECK.kind set and resumes no task.
 */
    .section .text.stack_fault, "ax"
    .type   stack_fault, %function
stack_fault:
stack_fault_guard:
    mov     r3, #1
    str     r1, [r12, #TC_VALUE]
    b       stack_fault_record
stack_fault_sp:
    mov     r3, #2
    mov     r1, sp
    str     r1, [r12, #TC_VALUE]
stack_fault_record:
    str     r3, [r12, #TC_KIND]
    str     r0, [r12, #TC_ADDR]
    ldr     sp, [r12, #TC_MAIN_SP]
    pop     {r4-r11, pc}
    .size   stack_fault, . - stack_fault

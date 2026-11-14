/*
 * switch.S - the cooperative context switch for the emulator-only task
 * experiment (tasks.rs, ADR 0003). QEMU `virt` test fixture, not OS code.
 *
 * Why this cannot be Rust (ADR 0001): a switch saves the callee-saved
 * registers r4-r11 and the return address of one call chain, stores its
 * stack pointer, loads another stack pointer and resumes the other chain.
 * Rust has no way to name those registers or to replace the stack pointer
 * in the middle of a function: the compiler owns sp and assumes it never
 * changes under it. So the switch is four instructions of assembly, and the
 * trampoline that starts a new task is three more. Everything else
 * (choosing the next task, checking the stack guard, the task table) is Rust.
 *
 * Calling convention (AAPCS, soft-float): r0-r3, r12 and lr are caller-saved,
 * so a call to ctx_switch from Rust only has to preserve r4-r11 and sp. There
 * is no VFP state: the build is soft-float (Makefile ARM_ARCH). Interrupts
 * stay masked (kstart.S), so nothing can run between the store and the load.
 */
    .syntax unified
    .arm

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
 * task_trampoline: the first code a new task runs. spawn() leaves the task's
 * entry function in r4 and its argument in r5 (initial frame), and this
 * address as the frame's saved lr. When the entry function returns, the task
 * is ended by task_exited (Rust), which never returns.
 */
    .section .text.task_trampoline, "ax"
    .global task_trampoline
    .type   task_trampoline, %function
task_trampoline:
    mov     r0, r5
    blx     r4
    bl      task_exited
    .size   task_trampoline, . - task_trampoline

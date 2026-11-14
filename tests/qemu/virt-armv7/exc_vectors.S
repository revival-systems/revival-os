/*
 * exc_vectors.S - exception vectors that report which exception happened and
 * where, then halt: an emulator-only step toward ROADMAP 3a, with exc.rs.
 * QEMU `virt` test fixture, not OS code, not Samsung code.
 *
 * Why this cannot be Rust (ADR 0001): the vector table is eight branch
 * instructions at fixed offsets from VBAR. An exception enters a different CPU
 * mode with its own banked stack pointer, which must be set before any Rust
 * runs. The return address the CPU leaves in lr is ahead of the faulting
 * instruction by an amount that depends on the exception. And VBAR and the
 * fault status and address registers (DFSR, DFAR, IFSR, IFAR) are CP15
 * registers that only mrc and mcr can reach. Everything else (naming the
 * exception, decoding the status, checking it, printing) is Rust.
 *
 * The two fault triggers at the end exist only for the tests: a fault whose
 * instruction has a known address lets a test check the reported address
 * exactly.
 */
    .syntax unified
    .arm

    .section .text.exc_vectors, "ax"
    .balign 32                      @ VBAR needs 32-byte alignment
exc_vectors:
    b       exc_reset
    b       exc_undef
    b       exc_svc
    b       exc_pabt
    b       exc_dabt
    b       exc_unused
    b       exc_irq
    b       exc_fiq

/*
 * Every stub calls exc_report(kind, pc, fsr, far) (Rust, never returns) on
 * the top of the main stack: r0 = the vector number, r1 = the address of the
 * instruction that caused the exception (lr minus this exception's offset in
 * ARM state), r2 = the fault status, r3 = the fault address (0 when the
 * exception has none).
 */
    .macro  report kind, offset
    sub     r1, lr, #\offset
    ldr     sp, =__stack_top
    mov     r0, #\kind
    bl      exc_report
    .endm

exc_reset:                          @ reset: no faulting instruction
    mov     lr, #0
    mov     r2, #0
    mov     r3, #0
    report  0, 0
exc_undef:                          @ lr = the undefined instruction + 4
    mov     r2, #0
    mov     r3, #0
    report  1, 4
exc_svc:                            @ lr = the svc instruction + 4
    mov     r2, #0
    mov     r3, #0
    report  2, 4
exc_pabt:                           @ lr = the instruction not fetched + 4
    mrc     p15, 0, r2, c5, c0, 1   @ IFSR
    mrc     p15, 0, r3, c6, c0, 2   @ IFAR
    report  3, 4
exc_dabt:                           @ lr = the faulting load or store + 8
    mrc     p15, 0, r2, c5, c0, 0   @ DFSR
    mrc     p15, 0, r3, c6, c0, 0   @ DFAR
    report  4, 8
exc_unused:
    mov     lr, #0
    mov     r2, #0
    mov     r3, #0
    report  5, 0
exc_irq:                            @ lr = the interrupted instruction + 4
    mov     r2, #0
    mov     r3, #0
    report  6, 4
exc_fiq:
    mov     r2, #0
    mov     r3, #0
    report  7, 4

/* install_exc_vectors(): VBAR = exc_vectors. */
    .section .text.install_exc_vectors, "ax"
    .global install_exc_vectors
    .type   install_exc_vectors, %function
install_exc_vectors:
    ldr     r0, =exc_vectors
    mcr     p15, 0, r0, c12, c0, 0  @ VBAR
    isb
    bx      lr
    .size   install_exc_vectors, . - install_exc_vectors

/* exc_udf(): an undefined instruction at a known address (test trigger). */
    .section .text.exc_udf, "ax"
    .global exc_udf
    .type   exc_udf, %function
exc_udf:
    udf     #0
    bx      lr
    .size   exc_udf, . - exc_udf

/* exc_load(addr) -> u32: a load at a known address (test trigger). */
    .section .text.exc_load, "ax"
    .global exc_load
    .type   exc_load, %function
exc_load:
    ldr     r0, [r0]
    bx      lr
    .size   exc_load, . - exc_load

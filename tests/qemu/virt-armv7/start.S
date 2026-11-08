/*
 * Entry stub for the Goose toolchain probe on QEMU virt (ARMv7-A, ARM state).
 * Test fixture only: not the Samsung boot stub.
 *
 * Masks interrupts, installs a vector table that reports any exception,
 * sets the stack, zeroes .bss, calls probe_main and exits with its result.
 */
    .syntax unified
    .arm

    .section .text.start, "ax"
    .global _start
_start:
    cpsid   if                      @ IRQ and FIQ masked
    ldr     r0, =vectors
    mcr     p15, 0, r0, c12, c0, 0  @ VBAR = vectors
    isb
    ldr     sp, =__stack_top
    ldr     r0, =__bss_start
    ldr     r1, =__bss_end
    mov     r2, #0
1:  cmp     r0, r1
    strlo   r2, [r0], #4
    blo     1b
    bl      probe_main              @ r0 = exit status
    bl      rt_exit                 @ does not return

    .section .text.vectors, "ax"
    .balign 32                      @ VBAR needs 32-byte alignment
vectors:
    b       vec_reset
    b       vec_undef
    b       vec_svc
    b       vec_pabt
    b       vec_dabt
    b       vec_unused
    b       vec_irq
    b       vec_fiq

    .macro  report n
    ldr     sp, =__stack_top
    mov     r0, #\n
    bl      rt_exception
    .endm

vec_reset:  report 0
vec_undef:  report 1
vec_svc:    report 2
vec_pabt:   report 3
vec_dabt:   report 4
vec_unused: report 5
vec_irq:    report 6
vec_fiq:    report 7

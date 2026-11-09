/*
 * kstart.S - ARMv7-A entry stub for the Phase 1 freestanding Rust kernel on
 * QEMU's `virt` board (ARM state). Phase 1 fixture only: NOT the Samsung boot
 * stub (the device's load address and handoff differ, docs/hardware/gt-i9195.md).
 *
 * Assembly is used here only for what Rust cannot express and what must run
 * before any Rust code exists (ADR 0001, docs/decisions/0001-rust-and-arm-assembly.md):
 *   - masking IRQ/FIQ and installing the exception vector table (VBAR);
 *   - setting the native Rust stack pointer from the linker script;
 *   - zeroing .bss before Rust reads any static;
 *   - the Arm semihosting SYS_EXIT instruction (the single, documented system-
 *     call instruction in the image; the Rust object contains none).
 * It then calls kmain (Rust). Faults are routed to kexception (Rust).
 */
    .syntax unified
    .arm

    .section .text.start, "ax"
    .global _start
_start:
    cpsid   if                      @ mask IRQ and FIQ
    ldr     r0, =vectors
    mcr     p15, 0, r0, c12, c0, 0  @ VBAR = vectors (32-byte aligned)
    isb
    ldr     sp, =__stack_top        @ native Rust call stack top (link.ld)
    ldr     r0, =__bss_start        @ zero .bss before Rust runs
    ldr     r1, =__bss_end
    mov     r2, #0
1:  cmp     r0, r1
    strlo   r2, [r0], #4
    blo     1b
    bl      kmain                   @ Rust; returns an i32 status in r0
    bl      rt_exit                 @ semihosting exit; does not return

/*
 * rt_exit(status): Arm semihosting SYS_EXIT. QEMU returns 0 for
 * ApplicationExit and 1 for a runtime error. Called from Rust (kmain's return,
 * the panic handler, and kexception). The `svc` below is the only system-call
 * instruction in the whole image.
 */
    .global rt_exit
rt_exit:
    ldr     r1, =0x20026            @ ADP_Stopped_ApplicationExit (status 0)
    cmp     r0, #0
    beq     1f
    ldr     r1, =0x20023            @ ADP_Stopped_RunTimeError (status != 0)
1:  mov     r0, #0x18               @ SYS_EXIT
    svc     0x123456
2:  wfi                             @ semihosting unavailable: hang; runner timeout fails
    b       2b

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
    ldr     sp, =__stack_top        @ reset SP in case of a corrupt stack
    mov     r0, #\n
    bl      kexception              @ Rust: prints the vector and exits 1
    .endm

vec_reset:  report 0
vec_undef:  report 1
vec_svc:    report 2
vec_pabt:   report 3
vec_dabt:   report 4
vec_unused: report 5
vec_irq:    report 6
vec_fiq:    report 7

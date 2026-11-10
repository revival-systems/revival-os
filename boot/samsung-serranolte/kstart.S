/*
 * kstart.S - GT-I9195 Phase 2 proof-of-execution entry stub (v1).
 *
 * This is DEVICE code: the ARM entry of the Android-boot-image kernel slot the
 * stock bootloader jumps to at 0x80208000 (docs/phase-2/boot-payload-research.md).
 * It is NOT the Phase 1 QEMU fixture (tests/qemu/virt-armv7/kstart.S); that stub
 * uses a semihosting `svc` and a different load address. This image contains NO
 * `svc` (and no `swi`/`smc`/`hvc`): it ends in a masked `wfi` loop forever.
 *
 * Assembly does only what must run before any Rust and what Rust cannot express
 * (ADR 0001): the zImage header the bootloader expects, capturing the handoff
 * state, masking interrupts, setting the stack, zeroing .bss, and the final halt.
 * Everything observable is painted by Rust (payload_main).
 *
 * The capture is position-independent: it reads r0-r3, CPSR, SCTLR and the
 * run-time entry address (adr _start) using no absolute loads, so the recorded
 * entry address reveals whether the bootloader honoured the 0x80208000 load
 * address. Only AFTER the capture does it use absolute symbols (stack, .bss),
 * which assume load == link; v1 proceeds on that assumption and paints the
 * captured entry address so a mismatch is visible in the photograph.
 */
    .syntax unified
    .arm

    .section .text.start, "ax"
    .global _start
_start:
    b       real_start              @ 0x00: branch over the zImage header
    .space  0x20, 0                 @ 0x04..0x24: reserved, never executed
    .word   0x016f2818              @ 0x24: zImage magic
    .word   0                       @ 0x28: zImage "start" (relative)
    .word   __image_size            @ 0x2c: zImage "end" = flat image size

real_start:
    @ --- capture handoff state (position-independent: no absolute loads) ------
    mov     r4, r0                  @ saved r0
    mov     r5, r1                  @ saved r1
    mov     r6, r2                  @ saved r2
    mov     r7, r3                  @ saved r3
    mrs     r8, cpsr                @ CPSR at entry (before masking)
    mrc     p15, 0, r9, c1, c0, 0   @ SCTLR (system control register)
    adr     r10, _start             @ run-time entry address

    @ --- mask IRQ and FIQ -----------------------------------------------------
    cpsid   if

    @ --- set the stack in the image's own static region (absolute) ------------
    ldr     sp, =__stack_top

    @ --- zero .bss before Rust reads any static ------------------------------
    ldr     r0, =__bss_start
    ldr     r1, =__bss_end
    mov     r2, #0
1:  cmp     r0, r1
    strlo   r2, [r0], #4
    blo     1b

    @ --- hand the 7 captured words to Rust as an on-stack array ---------------
    @ push stores the lowest register at the lowest address, so after this the
    @ stack holds, in order: [r4,r5,r6,r7,r8,r9,r10] = [r0,r1,r2,r3,cpsr,sctlr,entry].
    push    {r4-r10}
    mov     r0, sp                  @ r0 = &handoff[0]
    bl      payload_main            @ Rust; paints both framebuffers, returns

    @ --- halt forever, interrupts masked -------------------------------------
    @ halt_loop is a global symbol so the QEMU harness can resolve its address
    @ from the ELF and poll the PC until it rests here (no completion marker).
    .global halt_loop
halt_loop:
    wfi
    b       halt_loop

    .ltorg

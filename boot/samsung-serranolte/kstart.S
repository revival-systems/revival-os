/*
 * kstart.S - GT-I9195 Phase 2 proof-of-execution entry stub (v1.2).
 *
 * This is DEVICE code: the ARM entry of the Android-boot-image kernel slot the
 * stock bootloader jumps to at 0x80208000 (docs/phase-2/boot-payload-research.md).
 * It is NOT the Phase 1 QEMU fixture (tests/qemu/virt-armv7/kstart.S); that stub
 * uses a semihosting `svc` and a different load address. This image contains NO
 * `svc` (and no `swi`/`smc`/`hvc`): it ends in a masked `wfi` loop forever.
 *
 * Assembly does only what must run before any Rust and what Rust cannot express
 * (ADR 0001): the vector table and zImage header at the image base, capturing
 * the handoff state, masking interrupts, pointing VBAR at the image's own
 * vectors, setting the stack, zeroing .bss, and the final halt. Everything
 * observable is painted by Rust (payload_main).
 *
 * The first 0x30 bytes mirror lk2nd's arch/arm/crt0.S header exactly: a reset
 * branch, seven exception vectors, then a branch over the three zImage words
 * (which therefore stay at 0x24/0x28/0x2c). Every exception vector is a bare
 * `b halt_loop`. This is a SAFETY NET, not fault reporting: without it a fault
 * runs whatever vectors the bootloader left behind. A fault paints nothing,
 * uses no stack and runs no handler code; it only halts (Phase 3a reports).
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
    b       reset                   @ 0x00: reset / bootloader entry -> 0x20
    b       halt_loop               @ 0x04: undefined instruction
    b       halt_loop               @ 0x08: supervisor call (none in this image)
    b       halt_loop               @ 0x0c: prefetch abort
    b       halt_loop               @ 0x10: data abort
    b       halt_loop               @ 0x14: reserved
    b       halt_loop               @ 0x18: IRQ (masked; cannot be taken)
    b       halt_loop               @ 0x1c: FIQ (masked; cannot be taken)
reset:
    b       real_start              @ 0x20: branch over the zImage words
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

    @ --- exception safety net: VBAR = run-time _start (the table above) --------
    @ r10 is the address the image really runs at, so the table is found even if
    @ the bootloader loaded it elsewhere, and the vectors' branches are
    @ PC-relative. From here on any synchronous fault lands in halt_loop,
    @ provided SCTLR.V (bit 13, high vectors) is 0: this image does not write
    @ SCTLR, and the painted SCTLR row shows the bit (docs/phase-2).
    mcr     p15, 0, r10, c12, c0, 0 @ VBAR

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
    @ stack holds, in order: [r4,r5,r6,r7,r8,r9,r10] = [r0,r1,r2,r3,cpsr,sctlr,entry]
    @ followed by r11. r11 is not a captured value: it is an 8th word of padding
    @ so that sp stays 8-byte aligned at the call (AAPCS; __stack_top is 8-aligned
    @ and 8 words are pushed). Rust reads the first 7 words only.
    push    {r4-r11}
    mov     r0, sp                  @ r0 = &handoff[0]
    bl      payload_main            @ Rust; paints both framebuffers, returns

    @ --- halt forever, interrupts masked -------------------------------------
    @ Reached two ways: payload_main returned (CPU still in SVC mode), or an
    @ exception vector branched here (CPU in the exception's mode, with IRQ
    @ masked by the exception entry). halt_loop is a global symbol so the QEMU
    @ harness can resolve its address from the ELF and poll the PC until it
    @ rests here (no completion marker); the CPU mode tells the two apart.
    .global halt_loop
halt_loop:
    wfi
    b       halt_loop

    .ltorg

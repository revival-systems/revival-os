/*
 * link.ld - Link map for the GT-I9195 Phase 2 proof-of-execution payload (v1.2).
 *
 * The stock bootloader loads the kernel slot of an Android boot image at
 * 0x80208000 (base 0x80200000 + kernel_offset 0x8000), per the boot-image
 * parameters in docs/hardware/gt-i9195.md and docs/phase-2/boot-payload-research.md.
 * This is the DEVICE load address, not the Phase 1 QEMU fixture's 0x40000000.
 *
 * The flat binary (objcopy -O binary) spans the loaded sections only
 * (.text + .rodata + .data); .bss and the stack are NOLOAD and excluded, so
 * the image stays tiny. __image_size is (end of loaded data - _start); kstart.S
 * emits it as the zImage "end" word so the bootloader can find the (absent)
 * appended DTB, matching lk2nd's layout.
 *
 * The image's reserved span starts at 0x80208000 and ends well below 1 MiB,
 * far under the framebuffers at 0x88100000 / 0x88300000 and above ATAGS at
 * 0x80200100 (see the overlap table in docs/phase-2/boot-payload-research.md).
 */
ENTRY(_start)

__image_base = 0x80208000;

MEMORY
{
    /* Device RAM starts at 0x80000000; the image is loaded at the kernel slot.
       16 MiB is far more than the image needs and never reaches 0x88100000. */
    RAM (rwx) : ORIGIN = 0x80208000, LENGTH = 16M
}

/* Code and constants load read+execute, data read+write: no RWX segment. */
PHDRS
{
    text PT_LOAD FLAGS(5);  /* R X */
    data PT_LOAD FLAGS(6);  /* R W */
}

SECTIONS
{
    .text : ALIGN(4)
    {
        KEEP(*(.text.start))    /* _start: vectors + zImage header, image base */
        *(.text .text.*)
    } > RAM :text

    .rodata : ALIGN(8) { *(.rodata .rodata.*) } > RAM :text

    .ARM.exidx : { *(.ARM.exidx .ARM.exidx.*) } > RAM :text

    .data : ALIGN(8) { *(.data .data.*) } > RAM :data

    /* End of the loaded (flashed) image: the flat binary stops here. */
    . = ALIGN(4);
    __data_end = .;
    __image_size = __data_end - __image_base;

    .bss (NOLOAD) : ALIGN(8)
    {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > RAM :data

    /* The stack lives in the image's own reserved static region (NOLOAD). */
    .stack (NOLOAD) : ALIGN(8)
    {
        . += 64K;
        __stack_top = .;
    } > RAM :data

    /DISCARD/ : { *(.comment) *(.note .note.*) }
}

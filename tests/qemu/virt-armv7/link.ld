/* Link map for the Goose toolchain probe on QEMU virt (RAM at 0x40000000).
 * Test fixture only: the Samsung's load address is different
 * (docs/hardware/gt-i9195.md). */
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = 0x40000000, LENGTH = 16M
}

/* Code and constants load read+execute, data read+write: no RWX segment. */
PHDRS
{
    text PT_LOAD FLAGS(5);  /* R X */
    data PT_LOAD FLAGS(6);  /* R W */
}

SECTIONS
{
    .text : ALIGN(32)
    {
        KEEP(*(.text.start))
        KEEP(*(.text.vectors))
        *(.text .text.*)
    } > RAM :text

    .rodata : ALIGN(8) { *(.rodata .rodata.*) } > RAM :text

    .ARM.exidx : { *(.ARM.exidx .ARM.exidx.*) } > RAM :text

    .data : ALIGN(4096) { *(.data .data.*) } > RAM :data

    .bss (NOLOAD) : ALIGN(8)
    {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > RAM :data

    .stack (NOLOAD) : ALIGN(8)
    {
        . += 64K;
        __stack_top = .;
    } > RAM :data

    /DISCARD/ : { *(.comment) *(.note .note.*) }
}

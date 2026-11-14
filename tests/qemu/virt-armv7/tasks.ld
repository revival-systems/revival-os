/* Link map for the task experiment on QEMU virt (tasks.rs, ADR 0003).
 * Test fixture only. The same layout as link.ld (RAM at 0x40000000, the
 * symbols kstart.S needs), with two differences: a task arena after the
 * scheduler's stack, and a RAM region of 3 GiB less 1 MiB: the most a flat
 * 32-bit image at 0x40000000 can address below 4 GiB with the MMU off, so
 * that the measurement runs can size the arena up to the RAM QEMU is given
 * with -m (the region ends below 4 GiB, so no address wraps). The make check
 * images stay small (tests/qemu/run.sh gives QEMU 64M). An arena that does
 * not fit the RAM QEMU has faults when spawn() first paints past its end. */
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = 0x40000000, LENGTH = 3071M
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

    /* The task arena: (tasks + 1) stack slots, the lowest one an unused moat
     * between the scheduler's stack and the tasks' stacks. The Makefile gives
     * the size with --defsym=__task_arena_size=...; a link without it fails.
     * Not zeroed by kstart.S: spawn() paints each slot before a task uses it. */
    .task_arena (NOLOAD) : ALIGN(8)
    {
        __task_arena_start = .;
        . += __task_arena_size;
        __task_arena_end = .;
    } > RAM :data

    /DISCARD/ : { *(.comment) *(.note .note.*) }
}

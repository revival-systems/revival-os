/* Interface of the QEMU probe's freestanding runtime stub (minirt.c). */
#ifndef REVIVAL_TESTS_QEMU_MINIRT_H
#define REVIVAL_TESTS_QEMU_MINIRT_H

#include <stddef.h>
#include <stdint.h>

/* The allocator's fixed arena. calloc hands out zeroed blocks from it, each
 * a multiple of 8 bytes and 8-byte aligned, in address order, and never frees
 * them. It returns NULL when a request does not fit in what is left. A
 * zero-size request takes one block, so every non-NULL result is distinct. */
#define MINIRT_ARENA_BYTES 65536u

void *calloc(size_t count, size_t size);
void rt_puts(const char *s);
void rt_put_i64(int64_t v);
__attribute__((noreturn)) void rt_exit(int status);
__attribute__((noreturn)) void rt_exception(uint32_t vector);

#endif

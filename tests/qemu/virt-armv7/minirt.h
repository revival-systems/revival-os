/* Interface of the QEMU probe's freestanding runtime stub (minirt.c). */
#ifndef REVIVAL_TESTS_QEMU_MINIRT_H
#define REVIVAL_TESTS_QEMU_MINIRT_H

#include <stdint.h>

void rt_puts(const char *s);
void rt_put_i64(int64_t v);
__attribute__((noreturn)) void rt_exit(int status);
__attribute__((noreturn)) void rt_exception(uint32_t vector);

#endif

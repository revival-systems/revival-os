/*
 * Freestanding runtime stub for the Goose toolchain probe on QEMU's `virt`
 * board (ARMv7-A). Test fixture only: it is NOT the Revival OS runtime and
 * NOT code for the Samsung. It exists to show, by experiment, which runtime
 * entry points Goose-generated C needs when no C library or OS is present.
 *
 * It provides exactly the symbols the probe's generated C leaves undefined
 * (calloc, gs_panic, gs_idxfail and gs_rt_start_<runtime>), plus the four
 * memory functions GCC may emit calls to in freestanding code. Anything else
 * the generated C needs fails the link, which is the point of the test.
 *
 * The gs_* signatures are the Goose compiler's internal runtime interface,
 * copied from the C that the pinned compiler (tools/pins.env) emits. They are
 * versioned by the runtime hash in gs_rt_start's name, so a compiler change
 * makes this file fail to link instead of silently misbehaving.
 */
#include <stddef.h>
#include <stdint.h>

#include "minirt.h"

#ifndef GOOSE_RUNTIME_ID
#error "GOOSE_RUNTIME_ID must be defined (the GOOSE_RUNTIME pin from tools/pins.env)"
#endif

/* ---- QEMU virt platform: PL011 UART and Arm semihosting ---------------- */

#define UART0_BASE 0x09000000u /* QEMU virt UART0 (PL011) */
#define UART_DR (*(volatile uint32_t *)(UART0_BASE + 0x00u))
#define UART_FR (*(volatile uint32_t *)(UART0_BASE + 0x18u))
#define UART_FR_TXFF (1u << 5)

static void uart_putc(char c)
{
    while (UART_FR & UART_FR_TXFF) {
    }
    UART_DR = (uint32_t)(unsigned char)c;
}

void rt_puts(const char *s)
{
    while (*s != '\0') {
        uart_putc(*s++);
    }
}

void rt_put_i64(int64_t v)
{
    char buf[24];
    size_t n = 0;
    uint64_t u = v < 0 ? (uint64_t)0 - (uint64_t)v : (uint64_t)v;
    do {
        buf[n++] = (char)('0' + (int)(u % 10u));
        u /= 10u;
    } while (u != 0u);
    if (v < 0) {
        uart_putc('-');
    }
    while (n > 0) {
        uart_putc(buf[--n]);
    }
}

/* Semihosting SYS_EXIT (AArch32: r1 holds the reason code itself). QEMU
 * exits 0 for ApplicationExit and 1 for any other reason. */
#define SYS_EXIT 0x18u
#define ADP_STOPPED_APPLICATION_EXIT 0x20026u
#define ADP_STOPPED_RUNTIME_ERROR 0x20023u

void rt_exit(int status)
{
    uint32_t reason = status == 0 ? ADP_STOPPED_APPLICATION_EXIT : ADP_STOPPED_RUNTIME_ERROR;
    __asm__ volatile("mov r0, %0\n\t"
                     "mov r1, %1\n\t"
                     "svc 0x123456"
                     :
                     : "r"(SYS_EXIT), "r"(reason)
                     : "r0", "r1", "memory");
    for (;;) { /* semihosting unavailable: hang, and the runner's timeout fails the test */
        __asm__ volatile("wfi");
    }
}

/* Called by the vector stubs in start.S for any exception. */
void rt_exception(uint32_t vector)
{
    static volatile int nested;
    if (nested) {
        for (;;) {
            __asm__ volatile("wfi");
        }
    }
    nested = 1;
    rt_puts("probe: unexpected exception, vector ");
    rt_put_i64((int64_t)vector);
    rt_puts("\n");
    rt_exit(1);
}

/* ---- Memory functions GCC may call even in freestanding code ----------- */

void *memcpy(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    while (n-- > 0) {
        *d++ = *s++;
    }
    return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    if (d < s) {
        while (n-- > 0) {
            *d++ = *s++;
        }
    } else {
        while (n-- > 0) {
            d[n] = s[n];
        }
    }
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    unsigned char *d = dst;
    while (n-- > 0) {
        *d++ = (unsigned char)c;
    }
    return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *x = a;
    const unsigned char *y = b;
    for (; n > 0; n--, x++, y++) {
        if (*x != *y) {
            return *x < *y ? -1 : 1;
        }
    }
    return 0;
}

/* ---- Bounded allocator: a fixed arena, never freed --------------------- */

#define ARENA_BYTES 65536u
static unsigned char arena[ARENA_BYTES] __attribute__((aligned(8)));
static size_t arena_used;

void *calloc(size_t count, size_t size)
{
    if (size != 0 && count > SIZE_MAX / size) {
        return NULL;
    }
    size_t bytes = (count * size + 7u) & ~(size_t)7u;
    if (bytes > ARENA_BYTES - arena_used) {
        return NULL; /* the generated C reports this through gs_panic */
    }
    void *p = &arena[arena_used];
    arena_used += bytes;
    return p; /* .bss is zeroed by start.S, and nothing is ever freed */
}

/* ---- Goose runtime entry points used by the probe ---------------------- */

#define RT_CAT2(a, b) a##b
#define RT_CAT(a, b) RT_CAT2(a, b)
#define GS_RT_START RT_CAT(gs_rt_start_, GOOSE_RUNTIME_ID)

void GS_RT_START(int argc, char **argv, uint64_t reserve, uint64_t gap, uint64_t budget,
                 int64_t mainregions, int64_t workerregions);

void GS_RT_START(int argc, char **argv, uint64_t reserve, uint64_t gap, uint64_t budget,
                 int64_t mainregions, int64_t workerregions)
{
    (void)argc;
    (void)argv;
    (void)reserve;
    (void)gap;
    (void)budget;
    /* The probe uses no data stacks. A program that needs them must fail
     * loudly here rather than run without the regions it expects. */
    if (mainregions != 0 || workerregions != 0) {
        rt_puts("probe: program needs data-stack regions, which this stub does not provide\n");
        rt_exit(1);
    }
}

__attribute__((noreturn)) void gs_panic(const char *msg);
__attribute__((noreturn)) void gs_idxfail(int64_t i, int64_t n, const char *file, int line);

void gs_panic(const char *msg)
{
    rt_puts("panic: ");
    rt_puts(msg);
    rt_puts("\n");
    rt_exit(1);
}

void gs_idxfail(int64_t i, int64_t n, const char *file, int line)
{
    rt_puts("panic: index out of range: ");
    rt_put_i64(i);
    rt_puts(" not in [0, ");
    rt_put_i64(n);
    rt_puts(") at ");
    rt_puts(file);
    rt_puts(":");
    rt_put_i64(line);
    rt_puts("\n");
    rt_exit(1);
}

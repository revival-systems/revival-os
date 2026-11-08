/*
 * Boundary tests for the probe stub's allocator (calloc in minirt.c), run on
 * the ARMv7-A target under QEMU, where size_t is 32 bits. Test fixture only.
 *
 * start.S zeroes .bss and calls probe_main, so the arena is fresh and nothing
 * else allocates. The cases run in a fixed order and each prints one line;
 * the exit status is 0 only if all of them pass. The expected addresses
 * follow from the allocator's contract in minirt.h.
 */
#include <stddef.h>
#include <stdint.h>

#include "minirt.h"

#define ARENA ((size_t)MINIRT_ARENA_BYTES)
#define ANY_BLOCK UINTPTR_MAX /* expect: any 8-byte-aligned block */

static int cases;
static int failures;
static uintptr_t latest; /* what the last expect() got: blocks are never freed */

static void put_ptr(uintptr_t p)
{
    if (p == 0) {
        rt_puts("NULL");
        return;
    }
    char buf[2 * sizeof p + 1];
    for (size_t i = 0; i < 2 * sizeof p; i++) {
        buf[i] = "0123456789abcdef"[(p >> (4 * (2 * sizeof p - 1 - i))) & 0xfu];
    }
    buf[2 * sizeof p] = '\0';
    rt_puts("0x");
    rt_puts(buf);
}

static void verdict(int ok, const char *name)
{
    cases++;
    if (!ok) {
        failures++;
    }
    rt_puts(ok ? "alloc: ok   " : "alloc: FAIL ");
    rt_puts(name);
}

/* calloc(count, size) must return exactly want: 0 for NULL, or ANY_BLOCK.
 * The result is kept in `latest`. The sizes pass through volatile objects,
 * so the compiler cannot fold the call or reason about its arguments. */
static void expect(const char *name, size_t count, size_t size, uintptr_t want)
{
    volatile size_t c = count;
    volatile size_t s = size;
    latest = (uintptr_t)calloc(c, s);
    int ok = want == ANY_BLOCK ? latest != 0 && latest % 8u == 0 : latest == want;

    verdict(ok, name);
    rt_puts(": calloc(");
    rt_put_i64((int64_t)count);
    rt_puts(", ");
    rt_put_i64((int64_t)size);
    rt_puts(") = ");
    put_ptr(latest);
    if (!ok) {
        rt_puts(", expected ");
        if (want == ANY_BLOCK) {
            rt_puts("an 8-byte-aligned block");
        } else {
            put_ptr(want);
        }
    }
    rt_puts("\n");
}

static void check(const char *name, int ok)
{
    verdict(ok, name);
    rt_puts("\n");
}

static int all_zero(uintptr_t p, size_t n)
{
    const volatile unsigned char *b = (const volatile unsigned char *)p;
    for (size_t i = 0; i < n; i++) {
        if (b[i] != 0) {
            return 0;
        }
    }
    return 1;
}

int probe_main(void);

int probe_main(void)
{
    volatile size_t width = SIZE_MAX; /* read at run time, on the target */
    const size_t max = SIZE_MAX;

    rt_puts("alloc: start, arena of ");
    rt_put_i64((int64_t)ARENA);
    rt_puts(" bytes\n");
    check("target: size_t is 32 bits", width == 0xffffffffu);

    /* count * size does not fit in size_t: refused, and nothing is used. */
    expect("multiply-overflow", 0x10000u, 0x10000u, 0); /* 2^32 would wrap to 0 */
    expect("multiply-overflow", max / 2 + 1, 2, 0);     /* 2^32 would wrap to 0 */
    expect("multiply-overflow", 3, 0x55555556u, 0);     /* would wrap to 2 */
    expect("multiply-overflow", max, max, 0);           /* would wrap to 1 */

    /* The product fits in size_t, but rounding it up to 8 would wrap. */
    expect("round-overflow", 1, max, 0);         /* + 7 would wrap to 6 */
    expect("round-overflow", max, 1, 0);         /* + 7 would wrap to 6 */
    expect("round-overflow", 1, max - 6, 0);     /* + 7 would wrap to 0 */
    expect("round-overflow", 3, 0x55555553u, 0); /* 0xfffffff9: + 7 would wrap to 0 */

    /* Too large for the arena, with no wrap at all. */
    expect("too-large", 1, max - 7, 0); /* the largest size whose rounding does not wrap */
    expect("too-large", 1, ARENA + 1, 0);
    expect("too-large", ARENA + 1, 1, 0);
    expect("too-large", 2, ARENA / 2 + 1, 0);

    /* The first block starts the arena: the refusals above used none of it. */
    expect("first-block", 1, 1, ANY_BLOCK);
    const uintptr_t base = latest;

    /* Each block is the request rounded up to a multiple of 8. */
    expect("round-up", 1, 1, base + 8);  /* 1 byte takes 8 */
    expect("round-up", 3, 3, base + 16); /* 9 bytes take 16 */
    const uintptr_t nine = latest;
    expect("round-up", 2, 4, base + 32); /* 8 bytes take 8 */

    /* A zero-size request takes one block, so its result is distinct too. */
    expect("zero-size", 0, 16, base + 40);
    expect("zero-size", 16, 0, base + 48);
    expect("zero-size", 0, 0, base + 56);
    expect("zero-size", 0, max, base + 64);

    /* The rest of the arena, ARENA - 72 bytes, fits exactly, and not a byte more. */
    const size_t rest = ARENA - 72;
    expect("over-capacity", 1, rest + 1, 0);
    expect("over-capacity", rest / 8 + 1, 8, 0);
    expect("exact-capacity", rest / 8, 8, base + 72);
    const uintptr_t last = latest;

    /* The arena is full: every request is refused, zero-size ones too. */
    expect("exhausted", 1, 1, 0);
    expect("exhausted", 0, 1, 0);
    expect("exhausted", 1, max - 6, 0);

    check("zeroed: the 9-byte block and the last block read as zero",
          nine == base + 16 && last == base + 72 && all_zero(nine, 9) && all_zero(last, rest));

    rt_puts(failures == 0 ? "alloc: PASS (" : "alloc: FAIL (");
    rt_put_i64(cases - failures);
    rt_puts(" of ");
    rt_put_i64(cases);
    rt_puts(" cases)\n");
    return failures == 0 ? 0 : 1;
}

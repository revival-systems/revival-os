/*
 * Driver for the Goose toolchain probe on QEMU virt (ARMv7-A). Test fixture
 * only. start.S calls probe_main; its return value becomes the semihosting
 * exit status (0 = pass).
 *
 * PROBE_CASE selects the scenario (set by the Makefile):
 *   0  probe_checksum(PROBE_N) must equal PROBE_EXPECT, computed independently
 *      by tests/goose/checksum_oracle.py
 *   1  negative: probe_index(7) must fail through gs_idxfail, never return
 *   2  negative: hang, so that the runner's timeout must report a failure
 *   3  negative: execute an undefined instruction, so that the exception
 *      vectors must report it and exit with a failure
 */
#include <stdint.h>

#include "minirt.h"
#include "probe.h"

#ifndef PROBE_CASE
#error "PROBE_CASE must be defined"
#endif

int probe_main(void);

int probe_main(void)
{
    rt_puts("probe: start (case ");
    rt_put_i64(PROBE_CASE);
    rt_puts(")\n");
    goose_init(0, (char **)0);

#if PROBE_CASE == 0
    int32_t got = probe_checksum(PROBE_N);
    rt_puts("probe: probe_checksum(");
    rt_put_i64(PROBE_N);
    rt_puts(") = ");
    rt_put_i64(got);
    rt_puts("\n");
    if (got != (int32_t)PROBE_EXPECT) {
        rt_puts("probe: FAIL expected ");
        rt_put_i64(PROBE_EXPECT);
        rt_puts("\n");
        return 1;
    }
    rt_puts("probe: PASS\n");
    return 0;
#elif PROBE_CASE == 1
    int32_t v = probe_index(7);
    rt_puts("probe: FAIL probe_index(7) returned ");
    rt_put_i64(v);
    rt_puts(" instead of failing its bounds check\n");
    return 1;
#elif PROBE_CASE == 2
    rt_puts("probe: hanging on purpose\n");
    for (;;) {
        __asm__ volatile("" ::: "memory");
    }
#elif PROBE_CASE == 3
    rt_puts("probe: executing an undefined instruction on purpose\n");
    __asm__ volatile("udf #0");
    rt_puts("probe: FAIL the undefined instruction did not trap\n");
    return 1;
#else
#error "unknown PROBE_CASE"
#endif
}

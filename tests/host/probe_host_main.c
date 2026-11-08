/*
 * Host (Linux, hosted runtime) driver for tests/goose/probe.goose. It calls
 * the same exported functions as the QEMU driver, through the same
 * goose_init path, so that host and emulator results can be compared.
 *
 * Usage: probe_host checksum N | index I
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "probe.h"

static int parse_i64(const char *s, int64_t *out)
{
    char *end = NULL;
    errno = 0;
    long long v = strtoll(s, &end, 10);
    if (errno != 0 || end == s || *end != '\0') {
        return -1;
    }
    *out = (int64_t)v;
    return 0;
}

int main(int argc, char **argv)
{
    int64_t arg = 0;
    if (argc != 3 || parse_i64(argv[2], &arg) != 0) {
        fprintf(stderr, "usage: %s checksum N | index I\n", argv[0]);
        return 2;
    }
    goose_init(argc, argv);
    if (strcmp(argv[1], "checksum") == 0) {
        if (arg < 0 || arg > INT32_MAX) {
            fprintf(stderr, "N must be in [0, %d]\n", INT32_MAX);
            return 2;
        }
        printf("%d\n", (int)probe_checksum((int32_t)arg));
        return 0;
    }
    if (strcmp(argv[1], "index") == 0) {
        printf("%d\n", (int)probe_index(arg));
        return 0;
    }
    fprintf(stderr, "unknown command '%s'\n", argv[1]);
    return 2;
}

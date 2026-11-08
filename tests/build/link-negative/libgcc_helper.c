/* A deliberately bad link input (build-link-map-rejects-unapproved-libgcc):
 * a 64-bit division, which on ARMv7-A calls libgcc's __aeabi_uldivmod. */
#include <stdint.h>

uint64_t neg_entry(uint64_t a, uint64_t b);

uint64_t neg_entry(uint64_t a, uint64_t b)
{
    return a / b;
}

/* A deliberately bad link input (build-link-map-rejects-c-library): it calls
 * strlen, which only the C library (newlib's libc.a) defines. */
#include <stddef.h>

size_t strlen(const char *s);
size_t neg_entry(void);

size_t neg_entry(void)
{
    return strlen("hosted");
}

/* A deliberately bad link input (build-link-map-rejects-weak-unresolved): a
 * weak reference to a function that nothing defines. The link succeeds, and
 * the reference silently becomes address 0. */
int neg_missing(void) __attribute__((weak));
int neg_entry(void);

int neg_entry(void)
{
    return neg_missing ? neg_missing() : 0;
}

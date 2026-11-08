/* A deliberately bad link input (build-link-map-rejects-ignored-unresolved):
 * a reference to a function that nothing defines. The test links it with
 * --unresolved-symbols=ignore-all, so the linker accepts it. */
int neg_missing(void);
int neg_entry(void);

int neg_entry(void)
{
    return neg_missing();
}

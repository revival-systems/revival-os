/* A deliberately bad link input (build-link-map-rejects-unexpected-object):
 * harmless in itself, but not one of the objects the image may contain. */
int neg_entry(void);

int neg_entry(void)
{
    return 1;
}

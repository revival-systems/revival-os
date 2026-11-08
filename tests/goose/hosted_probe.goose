// Negative fixture: a program that needs the hosted runtime (the clock).
// Linking it against the QEMU probe's freestanding runtime stub must FAIL
// with undefined references. That failure shows the freestanding link check
// detects hosted dependencies instead of letting them through.
import os;

export "probe_clock" fn now() -> f64 {
    return clock();
}

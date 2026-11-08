// Freestanding toolchain probe (Phase 1 feasibility). Pure Goose, no imports:
// the same exports are built for the host (hosted runtime) and for ARMv7-A
// under QEMU (tests/qemu/virt-armv7), and must give the same results.

// Integer work whose result is easy to check independently:
// acc = acc * 31 + i for i in 0 .. n-1, wrapping at 32 bits (release builds
// wrap; --debug builds would report the overflow instead).
export "probe_checksum" fn checksum(n: i32) -> i32 {
    var acc: i32 = 0;
    var i: i32 = 0;
    while i < n {
        acc = acc * 31 + i;
        i = i + 1;
    }
    return acc;
}

// A bounds-checked read. probe_index(7) must fail through the runtime's
// panic path, not read past the table: the negative test relies on it.
export "probe_index" fn index(i: i64) -> i32 {
    let table: i32[4] = [10, 20, 30, 40];
    return table[i];
}

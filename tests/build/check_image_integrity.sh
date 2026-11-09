#!/usr/bin/env bash
# Corrupted-image detection (Phase 1 negative test, Test B). Given a freshly
# built kernel ELF, this records its SHA-256, makes a SEPARATE corrupted copy,
# proves the corrupted copy is REJECTED by the hash, and proves the ORIGINAL
# image is left byte-for-byte unchanged. It prints "PASS <name>" or
# "FAIL <name>: <reason>" lines (like tests/qemu/run.sh and tests/expect.sh)
# and exits nonzero on any failure.
#
# Usage: tests/build/check_image_integrity.sh IMAGE WORKDIR
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 IMAGE WORKDIR" >&2
    exit 2
fi
img=$1
work=$2
name=$(basename "$img")
mkdir -p "$work"

if [ ! -f "$img" ]; then
    echo "FAIL build-rust-corrupt-image-rejected: $img does not exist (run make build)"
    exit 1
fi

# Steps 1 and 2: the expected SHA-256 of the valid image.
expected=$(sha256sum "$img" | awk '{print $1}')

# Step 3: a separate corrupted copy - one byte flipped, the original untouched.
corrupt=$work/$name.corrupt
cp -- "$img" "$corrupt"
python3 -I - "$corrupt" <<'PY'
import sys
path = sys.argv[1]
with open(path, "rb") as fh:
    data = bytearray(fh.read())
# Flip the low bit of a middle byte: a guaranteed, minimal one-byte change.
data[len(data) // 2] ^= 0x01
with open(path, "wb") as fh:
    fh.write(data)
PY

# Step 4: the corrupted copy must be rejected. Its hash must differ, and a
# checklist verification (sha256sum -c) must report it as FAILED.
actual=$(sha256sum "$corrupt" | awk '{print $1}')
if [ "$actual" = "$expected" ]; then
    echo "FAIL build-rust-corrupt-image-rejected: the corrupted copy still matches the expected hash"
    exit 1
fi
checkfile=$work/$name.expected.sha256
printf '%s  %s\n' "$expected" "$corrupt" >"$checkfile"
if sha256sum -c "$checkfile" >/dev/null 2>&1; then
    echo "FAIL build-rust-corrupt-image-rejected: sha256sum -c accepted the corrupted copy"
    exit 1
fi
echo "PASS build-rust-corrupt-image-rejected ($name: a one-byte change is rejected by SHA-256)"

# Step 5: the original image must be byte-for-byte unchanged.
still=$(sha256sum "$img" | awk '{print $1}')
if [ "$still" != "$expected" ]; then
    echo "FAIL build-rust-image-unchanged: $name changed during the check (now $still, was $expected)"
    exit 1
fi
echo "PASS build-rust-image-unchanged ($name unchanged: $expected)"

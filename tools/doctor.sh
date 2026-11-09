#!/usr/bin/env bash
# Reports whether this machine can run the Revival OS local checks.
# Each tool is listed as ok, MISSING or WRONG with its version and, when it
# is not ok, how to fix it. Exits 1 if any tool that `make check` needs is
# not ok. Optional tools are reported but never fail the check.
#
# Usage: tools/doctor.sh   (normally through `make doctor`)
#
# Environment (set by the Makefile; defaults match tools/pins.env):
#   GOOSE    the pinned Goose compiler
#   ARM_BIN  the pinned Arm GNU Toolchain's bin directory
#   QEMU     the QEMU ARM system emulator
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tools/pins.env
. "$here/pins.env"

goose=${GOOSE:-$HOME/.local/share/goose/$GOOSE_VERSION/goose}
arm_bin=${ARM_BIN:-$HOME/.local/share/revival-os/toolchains/$ARM_TOOLCHAIN_NAME/bin}
qemu=${QEMU:-qemu-system-arm}
rust_prefix=${REVIVAL_RUST_PREFIX:-$HOME/.local/share/revival-os}
export RUSTUP_HOME=${RUSTUP_HOME:-$rust_prefix/rustup}
export CARGO_HOME=${CARGO_HOME:-$rust_prefix/cargo}
rustc_bin=${RUSTC:-$CARGO_HOME/bin/rustc}
apt_line="sudo apt install qemu-system-arm gdb-multiarch shellcheck cppcheck"
failed=0

row() { printf '  %-8s %-18s %s\n' "$1" "$2" "$3"; }

# required NAME CHECK-COMMAND FIX: CHECK-COMMAND prints a version on success.
required() {
    local name=$1 fix=$3 out
    if out=$(eval "$2" 2>/dev/null) && [ -n "$out" ]; then
        row ok "$name" "$out"
    else
        row MISSING "$name" "fix: $fix"
        failed=1
    fi
}

optional() {
    local name=$1 fix=$3 out
    if out=$(eval "$2" 2>/dev/null) && [ -n "$out" ]; then
        row ok "$name" "$out"
    else
        row absent "$name" "optional; $fix"
    fi
}

echo "Host"
row info os "$( (. /etc/os-release && echo "$PRETTY_NAME") 2>/dev/null) $(uname -m)"

echo "Required for make check"
required bash "bash --version | head -n 1" "install bash"
required make "make --version | head -n 1" "sudo apt install make"
required git "git --version" "sudo apt install git"
required python3 "python3 -c 'import sys; assert sys.version_info >= (3, 10); print(sys.version.split()[0])'" "Python 3.10 or newer"
required gcc "gcc --version | head -n 1" "sudo apt install gcc libc6-dev"
required timeout "command -v timeout >/dev/null && echo present" "coreutils"

# The pinned compilers: present AND exactly the pinned build.
if [ -x "$goose" ]; then
    bin_sha=$(sha256sum "$goose" | awk '{print $1}')
    version=$("$goose" version 2>/dev/null)
    if [ "$bin_sha" = "$GOOSE_BINARY_SHA256" ] && [ "$version" = "goose runtime $GOOSE_RUNTIME" ]; then
        row ok goose "$GOOSE_VERSION ($version, binary SHA-256 verified)"
    else
        row WRONG goose "$goose is not the pinned $GOOSE_VERSION build; fix: tools/install-goose.sh"
        failed=1
    fi
else
    row MISSING goose "fix: tools/install-goose.sh (pinned $GOOSE_VERSION)"
    failed=1
fi

if [ -x "$arm_bin/arm-none-eabi-gcc" ]; then
    marker=$(cat "$arm_bin/../.revival-archive-sha256" 2>/dev/null)
    line=$("$arm_bin/arm-none-eabi-gcc" --version | head -n 1)
    if [ "$marker" = "$ARM_TOOLCHAIN_SHA256" ]; then
        row ok arm-none-eabi "$line"
    else
        row WRONG arm-none-eabi "not installed from the pinned archive; fix: tools/install-arm-toolchain.sh"
        failed=1
    fi
else
    row MISSING arm-none-eabi "fix: tools/install-arm-toolchain.sh (pinned $ARM_TOOLCHAIN_VERSION)"
    failed=1
fi

# The pinned Rust toolchain and its bare-metal target (Phase 1+).
if [ -x "$rustc_bin" ]; then
    rust_line=$("$rustc_bin" --version 2>/dev/null || true)
    sysroot=$("$rustc_bin" --print sysroot 2>/dev/null || true)
    case "$rust_line" in
        "rustc $RUST_VERSION "*)
            if [ -n "$sysroot" ] && [ -d "$sysroot/lib/rustlib/$RUST_TARGET/lib" ]; then
                row ok rust "$rust_line (+ target $RUST_TARGET)"
            else
                row WRONG rust "rustc ok but target $RUST_TARGET is missing; fix: tools/install-rust.sh"
                failed=1
            fi
            ;;
        *)
            row WRONG rust "${rust_line:-not runnable} is not the pinned $RUST_VERSION; fix: tools/install-rust.sh"
            failed=1
            ;;
    esac
else
    row MISSING rust "fix: tools/install-rust.sh (pinned $RUST_VERSION, target $RUST_TARGET)"
    failed=1
fi

required qemu-system-arm "$qemu --version | head -n 1" "$apt_line"
required shellcheck "shellcheck --version | sed -n 2p" "$apt_line"
required cppcheck "cppcheck --version" "$apt_line"

echo "Optional"
optional gdb-multiarch "gdb-multiarch --version | head -n 1" "for make qemu-debug: $apt_line"
optional adb "adb version | head -n 1" "Phase 0 phone checklist only: sudo apt install adb android-sdk-platform-tools-common"
optional heimdall "heimdall version" "Phase 0 phone checklist only: sudo apt install heimdall-flash"

if [ "$failed" -ne 0 ]; then
    echo "doctor: some required tools are missing or wrong (see above)"
    exit 1
fi
echo "doctor: all required tools present"

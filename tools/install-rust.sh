#!/usr/bin/env bash
# Installs the pinned Rust bare-metal toolchain (rustc + target) for Revival OS
# into the user's home directory, isolated under ~/.local/share/revival-os.
# Downloads the official rustup-init, refuses it unless its SHA-256 matches the
# pin in tools/pins.env, then installs the pinned toolchain and target with no
# sudo and no shell-configuration change. Running it again only re-verifies.
#
# Usage: tools/install-rust.sh
#
# Environment:
#   REVIVAL_RUST_PREFIX  parent of the isolated install
#                        (default: ~/.local/share/revival-os)
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tools/pins.env
. "$here/pins.env"

prefix=${REVIVAL_RUST_PREFIX:-$HOME/.local/share/revival-os}
export RUSTUP_HOME=$prefix/rustup
export CARGO_HOME=$prefix/cargo
rustc_bin=$CARGO_HOME/bin/rustc
base=https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu

if [ "$(uname -s)/$(uname -m)" != "Linux/x86_64" ]; then
    echo "unsupported host $(uname -s)/$(uname -m): the pinned installer is for Linux x86_64" >&2
    exit 1
fi

if [ -x "$rustc_bin" ] && "$rustc_bin" --version 2>/dev/null | grep -q "rustc $RUST_VERSION "; then
    echo "already installed: $rustc_bin ($("$rustc_bin" --version))"
else
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/rust-install.XXXXXX")
    trap 'rm -rf "$tmp"' EXIT
    echo "downloading rustup-init from $base"
    curl --proto '=https' --tlsv1.2 -fsSL --retry 3 -o "$tmp/rustup-init" "$base/rustup-init"
    actual=$(sha256sum "$tmp/rustup-init" | awk '{print $1}')
    if [ "$actual" != "$RUSTUP_INIT_SHA256" ]; then
        echo "SHA-256 mismatch for rustup-init: got $actual, expected $RUSTUP_INIT_SHA256" >&2
        echo "(rustup may have published a newer installer; re-pin RUSTUP_INIT_SHA256 in review)" >&2
        exit 1
    fi
    echo "verified SHA-256 $actual"
    chmod +x "$tmp/rustup-init"
    "$tmp/rustup-init" -y --no-modify-path --profile minimal \
        --default-toolchain "$RUST_VERSION" -t "$RUST_TARGET"
    echo "installed: $rustc_bin"
fi

# Verified on every run: the pinned compiler and the target are present.
line=$("$rustc_bin" --version 2>/dev/null || true)
case "$line" in
    "rustc $RUST_VERSION "*) echo "$line" ;;
    *)
        echo "unexpected rustc at $rustc_bin: '$line' (pinned $RUST_VERSION)" >&2
        exit 1
        ;;
esac
sysroot=$("$rustc_bin" --print sysroot)
if [ ! -d "$sysroot/lib/rustlib/$RUST_TARGET/lib" ]; then
    echo "target $RUST_TARGET is not installed in $sysroot; fix: rustup target add $RUST_TARGET" >&2
    exit 1
fi
echo "target $RUST_TARGET: present"
echo "cargo bin: $CARGO_HOME/bin (the Makefile finds rustc there; no PATH change needed)"

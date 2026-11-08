#!/usr/bin/env bash
# Installs the pinned Goose compiler release (Linux x86_64) for Revival OS.
# Downloads the upstream prebuilt archive, refuses it unless its SHA-256
# matches tools/pins.env, unpacks the whole distribution into one versioned
# directory, and verifies the compiler binary and its runtime version on
# every run. Needs no sudo and changes no shell configuration.
#
# Provenance: adapted from revival-server scripts/install-goose-linux.sh at
# commit fc6848ed2c107f5fbb5110393527ab23e9a9e7fb. The pin is the same, and the
# default location is the same, so one install serves both projects.
#
# Usage: tools/install-goose.sh
#
# Environment:
#   GOOSE_PREFIX  parent of the versioned install (default: ~/.local/share/goose)
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tools/pins.env
. "$here/pins.env"

prefix=${GOOSE_PREFIX:-$HOME/.local/share/goose}
dest=$prefix/$GOOSE_VERSION
expected_runtime="goose runtime $GOOSE_RUNTIME"

if [ "$(uname -s)/$(uname -m)" != "Linux/x86_64" ]; then
    echo "unsupported host $(uname -s)/$(uname -m): upstream publishes a Linux release for x86_64 only" >&2
    exit 1
fi

if [ -x "$dest/goose" ]; then
    echo "already installed: $dest"
else
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/goose-install.XXXXXX")
    trap 'rm -rf "$tmp"' EXIT
    url=https://github.com/aardappel/goose/releases/download/$GOOSE_VERSION/$GOOSE_ASSET
    echo "downloading $url"
    curl -fsSL --retry 3 -o "$tmp/$GOOSE_ASSET" "$url"
    actual=$(sha256sum "$tmp/$GOOSE_ASSET" | awk '{print $1}')
    if [ "$actual" != "$GOOSE_ASSET_SHA256" ]; then
        echo "SHA-256 mismatch for $GOOSE_ASSET: got $actual, expected $GOOSE_ASSET_SHA256" >&2
        exit 1
    fi
    echo "verified SHA-256 $actual"
    mkdir -p "$tmp/unpacked" "$prefix"
    tar -xzf "$tmp/$GOOSE_ASSET" -C "$tmp/unpacked"
    top=$(find "$tmp/unpacked" -mindepth 1 -maxdepth 1)
    if [ "$(printf '%s\n' "$top" | wc -l)" -ne 1 ] || [ ! -x "$top/goose" ]; then
        echo "unexpected layout in $GOOSE_ASSET: no single directory holding goose" >&2
        exit 1
    fi
    mv "$top" "$dest"
    echo "installed: $dest"
fi

actual_bin=$(sha256sum "$dest/goose" | awk '{print $1}')
if [ "$actual_bin" != "$GOOSE_BINARY_SHA256" ]; then
    echo "SHA-256 mismatch for $dest/goose: got $actual_bin, expected $GOOSE_BINARY_SHA256" >&2
    exit 1
fi
runtime=$("$dest/goose" version)
if [ "$runtime" != "$expected_runtime" ]; then
    echo "unexpected compiler at $dest: '$runtime', expected '$expected_runtime'" >&2
    exit 1
fi
echo "$runtime"
echo "compiler: $dest/goose (the Makefile finds it there; no PATH change needed)"

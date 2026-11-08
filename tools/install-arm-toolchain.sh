#!/usr/bin/env bash
# Installs the pinned Arm GNU Toolchain (arm-none-eabi, x86_64 Linux host)
# into the user's home directory. Downloads Arm's official release archive,
# refuses it unless its SHA-256 matches the pin in tools/pins.env, and unpacks
# it into one versioned directory. Needs no sudo and changes no shell
# configuration. Running it again only re-verifies the install.
#
# Usage: tools/install-arm-toolchain.sh
#
# Environment:
#   REVIVAL_TOOLCHAINS  parent directory of the install
#                       (default: ~/.local/share/revival-os/toolchains)
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tools/pins.env
. "$here/pins.env"

prefix=${REVIVAL_TOOLCHAINS:-$HOME/.local/share/revival-os/toolchains}
dest=$prefix/$ARM_TOOLCHAIN_NAME
asset=$ARM_TOOLCHAIN_NAME.tar.xz
url=https://developer.arm.com/-/media/Files/downloads/gnu/$ARM_TOOLCHAIN_VERSION/binrel/$asset
marker=$dest/.revival-archive-sha256

if [ "$(uname -s)/$(uname -m)" != "Linux/x86_64" ]; then
    echo "unsupported host $(uname -s)/$(uname -m): the pinned archive is for Linux x86_64" >&2
    exit 1
fi

if [ -x "$dest/bin/arm-none-eabi-gcc" ]; then
    echo "already installed: $dest"
else
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/arm-toolchain.XXXXXX")
    trap 'rm -rf "$tmp"' EXIT
    echo "downloading $url"
    curl -fsSL --retry 3 -o "$tmp/$asset" "$url"
    actual=$(sha256sum "$tmp/$asset" | awk '{print $1}')
    if [ "$actual" != "$ARM_TOOLCHAIN_SHA256" ]; then
        echo "SHA-256 mismatch for $asset: got $actual, expected $ARM_TOOLCHAIN_SHA256" >&2
        exit 1
    fi
    echo "verified SHA-256 $actual"
    mkdir -p "$tmp/unpacked" "$prefix"
    tar -xJf "$tmp/$asset" -C "$tmp/unpacked"
    if [ ! -x "$tmp/unpacked/$ARM_TOOLCHAIN_NAME/bin/arm-none-eabi-gcc" ]; then
        echo "unexpected layout in $asset: no $ARM_TOOLCHAIN_NAME/bin/arm-none-eabi-gcc" >&2
        exit 1
    fi
    mv "$tmp/unpacked/$ARM_TOOLCHAIN_NAME" "$dest"
    echo "$actual" > "$marker"
    echo "installed: $dest"
fi

# Checked on every run: an install this script did not make is refused.
if [ "$(cat "$marker" 2>/dev/null)" != "$ARM_TOOLCHAIN_SHA256" ]; then
    echo "$dest was not installed from the pinned archive (missing or wrong $marker)" >&2
    exit 1
fi
version_line=$("$dest/bin/arm-none-eabi-gcc" --version | head -n 1)
case "$version_line" in
    *"${ARM_TOOLCHAIN_VERSION%.rel1}"*) echo "$version_line" ;;
    *)
        echo "unexpected compiler at $dest: '$version_line' (pinned $ARM_TOOLCHAIN_VERSION)" >&2
        exit 1
        ;;
esac
echo "bin directory: $dest/bin (the Makefile finds it there; no PATH change needed)"

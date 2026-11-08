#!/usr/bin/env bash
# Runs a command and checks its exit status and output. Prints one line,
# "PASS <name>" or "FAIL <name>: <reason>", keeps stdout and stderr in <log>,
# and exits 0 only on PASS. Used for host tests and for tests that must fail.
#
# Usage:
#   tests/expect.sh NAME STATUS TEXT LOG -- COMMAND [ARGS...]
#     STATUS  the exact exit status expected, or "nonzero"
#     TEXT    a fixed string the combined output must contain ("" = no check)
set -euo pipefail

if [ "$#" -lt 6 ] || [ "$5" != "--" ]; then
    echo "usage: $0 NAME STATUS TEXT LOG -- COMMAND [ARGS...]" >&2
    exit 2
fi
name=$1 expect=$2 text=$3 log=$4
shift 5

set +e
"$@" >"$log" 2>&1
status=$?
set -e

if [ "$expect" = nonzero ]; then
    if [ "$status" -eq 0 ]; then
        echo "FAIL $name: expected a failure, but it exited 0 (log: $log)"
        exit 1
    fi
elif [ "$status" -ne "$expect" ]; then
    echo "FAIL $name: exited $status, expected $expect (log: $log)"
    exit 1
fi

if [ -n "$text" ] && ! grep -qF -- "$text" "$log"; then
    echo "FAIL $name: output lacks '$text' (log: $log)"
    exit 1
fi
echo "PASS $name"

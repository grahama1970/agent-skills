#!/bin/bash

set -euo pipefail

if [[ "$1" == "benchmark" ]]; then
    shift
    python3 -m benchmark "$@"
else
    echo "Unknown command: $1"
    exit 1
fi
#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: ./run.sh <raw_dir> <out_dir>"
    exit 1
fi

RAW_DIR="$1"
OUT_DIR="$2"

mkdir -p "$OUT_DIR"

python3 -m src.pipeline "$RAW_DIR" "$OUT_DIR"

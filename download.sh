#!/usr/bin/env bash
set -euo pipefail

RAW_DIR="${1:-raw}"
mkdir -p "$RAW_DIR"

echo "=== Downloading Raw Datasets into: $RAW_DIR ==="

# Source 1: Hindi Wikipedia Dump (.xml.bz2)
# License: CC BY-SA 3.0 | https://dumps.wikimedia.org/hiwiki/latest/
HIWIKI_URL="https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2"
HIWIKI_TARGET="$RAW_DIR/hiwiki-latest-pages-articles.xml.bz2"

if [ -f "$HIWIKI_TARGET" ] || [ -f "$RAW_DIR/hiwiki-latest-pages-articles.xml" ] || [ -f "hiwiki-latest-pages-articles.xml" ] || [ -f "hiwiki-latest-pages-articles.xml.bz2" ]; then
    echo "[Source 1] Hindi Wikipedia dump already present. Skipping download."
    # If present in current dir but not in RAW_DIR, create a hardlink or symlink into RAW_DIR
    if [ ! -f "$RAW_DIR/hiwiki-latest-pages-articles.xml" ] && [ -f "hiwiki-latest-pages-articles.xml" ]; then
        ln "hiwiki-latest-pages-articles.xml" "$RAW_DIR/hiwiki-latest-pages-articles.xml" 2>/dev/null || cp "hiwiki-latest-pages-articles.xml" "$RAW_DIR/hiwiki-latest-pages-articles.xml"
    fi
else
    echo "[Source 1] Downloading Hindi Wikipedia dump (.xml.bz2)..."
    curl -L --retry 3 -o "$HIWIKI_TARGET" "$HIWIKI_URL"
    echo "[Source 1] Hindi Wikipedia dump downloaded successfully."
fi

# Source 2: Google Research Hinglish-TOP Dataset (.tsv)
# License: Apache 2.0 | https://github.com/google-research-datasets/Hinglish-TOP-Dataset
HINGLISH_URL="https://raw.githubusercontent.com/google-research-datasets/Hinglish-TOP-Dataset/main/Dataset/Human%20Annotated%20Data/train.tsv"
HINGLISH_TARGET="$RAW_DIR/hinglish_top_train.tsv"

if [ -f "$HINGLISH_TARGET" ]; then
    echo "[Source 2] Hinglish-TOP dataset already present. Skipping download."
else
    echo "[Source 2] Downloading Hinglish-TOP dataset (.tsv)..."
    curl -L --retry 3 -o "$HINGLISH_TARGET" "$HINGLISH_URL"
    echo "[Source 2] Hinglish-TOP dataset downloaded successfully."
fi

echo "=== Download Complete ==="
ls -lh "$RAW_DIR"

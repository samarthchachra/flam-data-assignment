import argparse
import csv
import gzip
import hashlib
import json
import os
import time
from typing import Dict, Any

from src.ingest import StreamingIngestor
from src.normalize import normalize_document
from src.lang_label import label_document
from src.quality_filter import filter_document
from src.dedup import Deduplicator
from src.pii_redact import redact_document


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of an input file for the manifest."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_pipeline(raw_dir: str, out_dir: str, near_dedup_threshold: float = 0.80):
    start_time = time.time()
    clean_dir = os.path.join(out_dir, "clean")
    os.makedirs(clean_dir, exist_ok=True)

    clean_file_path = os.path.join(clean_dir, "train.jsonl.gz")
    ledger_file_path = os.path.join(out_dir, "ledger.csv")
    manifest_file_path = os.path.join(out_dir, "manifest.json")

    # Counts for manifest & funnel
    counts = {
        "raw_scanned": 0,
        "dropped_ingest": 0,
        "dropped_quality_filter": 0,
        "dropped_exact_dedup": 0,
        "dropped_near_dedup": 0,
        "kept_total": 0,
        "kept_by_lang": {"hi": 0, "hi-Latn": 0, "en or other": 0}
    }

    # Record input file hashes
    input_hashes = {}
    for fname in sorted(os.listdir(raw_dir)):
        fpath = os.path.join(raw_dir, fname)
        if os.path.isfile(fpath) and not fname.startswith("."):
            input_hashes[fname] = compute_file_sha256(fpath)

    ingestor = StreamingIngestor(max_wiki_docs=15000)
    deduplicator = Deduplicator(near_dedup_threshold=near_dedup_threshold)

    with gzip.open(clean_file_path, "wt", encoding="utf-8") as clean_out, \
         open(ledger_file_path, "w", encoding="utf-8", newline="") as ledger_out:

        ledger_writer = csv.DictWriter(
            ledger_out,
            fieldnames=["id", "status", "stage", "reason", "dup_of"]
        )
        ledger_writer.writeheader()

        # STAGE 1: INGEST
        for doc, drop in ingestor.ingest_directory(raw_dir):
            counts["raw_scanned"] += 1

            if drop:
                counts["dropped_ingest"] += 1
                ledger_writer.writerow(drop)
                continue

            # STAGE 2: NORMALIZE UNICODE
            doc = normalize_document(doc)

            # STAGE 3: LABEL LANGUAGE
            doc = label_document(doc)

            # STAGE 4: QUALITY FILTER & MARKUP STRIPPING
            doc, drop = filter_document(doc)
            if drop:
                counts["dropped_quality_filter"] += 1
                ledger_writer.writerow(drop)
                continue

            # STAGE 5: DEDUPLICATION (Exact & Near)
            doc, drop = deduplicator.process_document(doc)
            if drop:
                if drop["reason"] == "exact_duplicate":
                    counts["dropped_exact_dedup"] += 1
                else:
                    counts["dropped_near_dedup"] += 1
                ledger_writer.writerow(drop)
                continue

            # STAGE 6: PII REDACTION
            doc = redact_document(doc)

            # STAGE 7: KEPT DOCUMENT (Write to clean & ledger)
            clean_record = {
                "id": doc["id"],
                "text": doc["text"],
                "lang": doc["lang"],
                "source": doc["source"]
            }
            clean_out.write(json.dumps(clean_record, ensure_ascii=False) + "\n")

            ledger_writer.writerow({
                "id": doc["id"],
                "status": "kept",
                "stage": "final",
                "reason": "",
                "dup_of": ""
            })

            counts["kept_total"] += 1
            counts["kept_by_lang"][doc["lang"]] += 1

    elapsed = time.time() - start_time

    # STAGE 8: WRITE MANIFEST
    manifest = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 2),
        "thresholds": {
            "near_dedup_jaccard": near_dedup_threshold,
            "min_words": 3,
            "min_chars": 15,
            "max_symbol_ratio": 0.40,
            "max_numeric_ratio": 0.70
        },
        "input_file_hashes": input_hashes,
        "stage_counts": counts
    }

    with open(manifest_file_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Pipeline finished in {elapsed:.2f}s.")
    print(f"Total Scanned: {counts['raw_scanned']} | Kept: {counts['kept_total']}")
    print(f"Kept by Lang: {counts['kept_by_lang']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="End-to-end Indic Curation Pipeline")
    parser.add_argument("raw_dir", help="Directory containing raw data files")
    parser.add_argument("out_dir", help="Directory to save curated output")
    parser.add_argument("--threshold", type=float, default=0.80, help="Near-dedup Jaccard threshold")
    args = parser.parse_args()

    run_pipeline(args.raw_dir, args.out_dir, near_dedup_threshold=args.threshold)

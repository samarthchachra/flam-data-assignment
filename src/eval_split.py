import gzip
import json
import os
import random
from typing import Dict, Any, List

EVAL_BENCHMARK_DESCRIPTION = (
    "Measures natural Hindi reading comprehension and code-mixed Hinglish intent "
    "understanding on held-out user queries and encyclopedic excerpts."
)

def create_eval_split(
    clean_train_gz: str,
    output_eval_jsonl: str,
    num_hindi: int = 150,
    num_hinglish: int = 50,
    seed: int = 42
):
    """
    Selects 150 Hindi and 50 Hinglish documents deterministically,
    writes them to eval.jsonl, and removes them from clean/train.jsonl.gz.
    """
    rng = random.Random(seed)

    # 1. First pass: Collect candidate IDs partitioned by language
    hindi_candidates: List[Dict[str, Any]] = []
    hinglish_candidates: List[Dict[str, Any]] = []

    with gzip.open(clean_train_gz, "rt", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            if doc.get("lang") == "hi":
                hindi_candidates.append(doc)
            elif doc.get("lang") == "hi-Latn":
                hinglish_candidates.append(doc)

    # Sample deterministically
    selected_hindi = rng.sample(hindi_candidates, min(num_hindi, len(hindi_candidates)))
    selected_hinglish = rng.sample(hinglish_candidates, min(num_hinglish, len(hinglish_candidates)))

    eval_docs = selected_hindi + selected_hinglish
    eval_ids = {doc["id"] for doc in eval_docs}

    # 2. Write held-out eval set (including the 1-line benchmark description)
    with open(output_eval_jsonl, "w", encoding="utf-8") as out_eval:
        for doc in eval_docs:
            eval_record = {
                "eval_id": doc["id"],
                "text": doc["text"],
                "lang": doc["lang"],
                "source": doc["source"],
                "benchmark_target": EVAL_BENCHMARK_DESCRIPTION
            }
            out_eval.write(json.dumps(eval_record, ensure_ascii=False) + "\n")

    # 3. Second pass: Rewrite clean/train.jsonl.gz excluding eval documents
    temp_train_path = clean_train_gz + ".tmp"
    remaining_train_count = 0

    with gzip.open(clean_train_gz, "rt", encoding="utf-8") as src, \
         gzip.open(temp_train_path, "wt", encoding="utf-8") as dst:
        for line in src:
            doc = json.loads(line)
            if doc["id"] not in eval_ids:
                dst.write(line)
                remaining_train_count += 1

    # Atomic replace to prevent data corruption
    os.replace(temp_train_path, clean_train_gz)

    print(f"Created {len(eval_docs)} eval documents ({len(selected_hindi)} hi, {len(selected_hinglish)} hi-Latn).")
    print(f"Saved to: {output_eval_jsonl}")
    print(f"Remaining training documents in {clean_train_gz}: {remaining_train_count}")


if __name__ == "__main__":
    create_eval_split(
        clean_train_gz="output/clean/train.jsonl.gz",
        output_eval_jsonl="output/eval.jsonl",
        num_hindi=150,
        num_hinglish=50
    )

import gzip
import json
import os
import re
from typing import Dict, List, Set, Any

# Lightweight rule-based Devanagari to Latin phonetic transliterator for cross-script check
DEV_TO_LATIN_MAP = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "औ": "au",
    "्": "", "ं": "n", "ः": "h", "़": ""
}

def transliterate_to_latin(text: str) -> str:
    """Converts Devanagari characters to Romanized phonetic approximations."""
    res = []
    for char in text:
        res.append(DEV_TO_LATIN_MAP.get(char, char))
    return "".join(res).lower()

def normalize_for_check(text: str) -> str:
    """Collapses spaces and punctuation for normalized comparison."""
    return re.sub(r"\W+", "", text).lower()

def get_char_shingles(text: str, k: int = 5) -> Set[str]:
    clean = "".join(text.split()).lower()
    if len(clean) < k:
        return {clean}
    return {clean[i:i + k] for i in range(len(clean) - k + 1)}

def check_contamination(
    eval_jsonl_path: str,
    train_gz_path: str,
    contamination_jsonl_path: str,
    near_threshold: float = 0.80
):
    print("=== Running Contamination Check ===")

    # 1. Load eval items and build lookup indices
    eval_items: List[Dict] = []
    eval_exact_index: Dict[str, str] = {}       # exact text -> eval_id
    eval_norm_index: Dict[str, str] = {}        # normalized text -> eval_id
    eval_shingles: Dict[str, Set[str]] = {}     # eval_id -> shingles
    eval_cross_script: Dict[str, str] = {}      # transliterated text -> eval_id

    with open(eval_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            eid = item["eval_id"]
            text = item["text"]
            eval_items.append(item)

            eval_exact_index[text] = eid
            eval_norm_index[normalize_for_check(text)] = eid
            eval_shingles[eid] = get_char_shingles(text, k=5)

            # Build cross-script index for Devanagari eval items
            if item["lang"] == "hi":
                romanized = transliterate_to_latin(text)
                eval_cross_script[normalize_for_check(romanized)] = eid

    # 2. Stream through train set and check for leaks
    affected_evals: Dict[str, Dict[str, Any]] = {}
    leaking_train_ids: Set[str] = set()

    with gzip.open(train_gz_path, "rt", encoding="utf-8") as f:
        for line in f:
            tdoc = json.loads(line)
            tid = tdoc["id"]
            ttext = tdoc["text"]
            tnorm = normalize_for_check(ttext)
            tlang = tdoc["lang"]

            matched_eid = None
            method = None

            # Check 1: Exact match
            if ttext in eval_exact_index:
                matched_eid = eval_exact_index[ttext]
                method = "exact"

            # Check 2: Normalized match
            elif tnorm in eval_norm_index:
                matched_eid = eval_norm_index[tnorm]
                method = "normalized"

            # Check 3: Cross-script transliteration match (Devanagari eval in Latin train)
            elif tlang == "hi-Latn" and tnorm in eval_cross_script:
                matched_eid = eval_cross_script[tnorm]
                method = "cross_script"

            # Check 4: Near-duplicate match (Jaccard similarity >= 0.80)
            else:
                tshingles = get_char_shingles(ttext, k=5)
                for eid, eshingles in eval_shingles.items():
                    intersection = len(tshingles.intersection(eshingles))
                    union = len(tshingles.union(eshingles))
                    sim = intersection / union if union > 0 else 0
                    if sim >= near_threshold:
                        matched_eid = eid
                        method = f"near_copy_sim_{sim:.2f}"
                        break

            if matched_eid:
                leaking_train_ids.add(tid)
                if matched_eid not in affected_evals:
                    affected_evals[matched_eid] = {
                        "eval_id": matched_eid,
                        "train_ids": [],
                        "method": method
                    }
                affected_evals[matched_eid]["train_ids"].append(tid)

    # 3. Write contamination.jsonl
    with open(contamination_jsonl_path, "w", encoding="utf-8") as f:
        for record in affected_evals.values():
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 4. Remove leaking training documents if any found
    if leaking_train_ids:
        temp_train = train_gz_path + ".leak_purge.tmp"
        purged_count = 0
        with gzip.open(train_gz_path, "rt", encoding="utf-8") as src, \
             gzip.open(temp_train, "wt", encoding="utf-8") as dst:
            for line in src:
                doc = json.loads(line)
                if doc["id"] not in leaking_train_ids:
                    dst.write(line)
                else:
                    purged_count += 1
        os.replace(temp_train, train_gz_path)
        print(f"Purged {purged_count} leaking documents from {train_gz_path}.")
    else:
        print("Zero leaks detected in the training set.")

    print(f"Affected eval items: {len(affected_evals)}")
    print(f"Report written to: {contamination_jsonl_path}")


if __name__ == "__main__":
    check_contamination(
        eval_jsonl_path="output/eval.jsonl",
        train_gz_path="output/clean/train.jsonl.gz",
        contamination_jsonl_path="output/contamination.jsonl"
    )

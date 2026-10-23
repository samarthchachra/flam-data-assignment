import hashlib
import random
from typing import Tuple, Optional, Dict, Any, Set, List

# Fixed random seed for 100% deterministic MinHash signatures across runs
RANDOM_SEED = 42
NUM_PERMUTATIONS = 64
NUM_BANDS = 16
ROWS_PER_BAND = 4  # 16 bands * 4 rows = 64 hashes (high recall for candidate retrieval)
PRIME = (1 << 61) - 1

# Generate deterministic hash coefficients
rng = random.Random(RANDOM_SEED)
A_COEFFS = [rng.randint(1, PRIME - 1) for _ in range(NUM_PERMUTATIONS)]
B_COEFFS = [rng.randint(0, PRIME - 1) for _ in range(NUM_PERMUTATIONS)]


def get_shingles(text: str, k: int = 5) -> Set[str]:
    """Generates character k-grams from text."""
    text = "".join(text.split()).lower()
    if len(text) < k:
        return {text}
    return {text[i:i + k] for i in range(len(text) - k + 1)}


def compute_minhash(shingles: Set[str]) -> List[int]:
    """Computes a 64-integer MinHash signature for a set of shingles."""
    shingle_hashes = [
        int.from_bytes(hashlib.md5(s.encode("utf-8")).digest()[:8], "little")
        for s in shingles
    ]
    if not shingle_hashes:
        return [0] * NUM_PERMUTATIONS

    signature = []
    for a, b in zip(A_COEFFS, B_COEFFS):
        min_val = min(((a * h + b) % PRIME) for h in shingle_hashes)
        signature.append(min_val)
    return signature


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Computes exact Jaccard similarity between two shingle sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


class Deduplicator:
    """
    Handles exact (SHA-256) and near-duplicate (MinHash LSH) deduplication.
    Tracks original document IDs for the audit ledger.
    """

    def __init__(self, near_dedup_threshold: float = 0.80):
        self.threshold = near_dedup_threshold
        self.seen_exact_hashes: Dict[str, str] = {}  # sha256 -> doc_id
        self.lsh_buckets: Dict[Tuple[int, Tuple[int, ...]], List[str]] = {}
        self.doc_shingles: Dict[str, Set[str]] = {}

    def check_duplicate(self, doc_id: str, text: str) -> Tuple[bool, str, str]:
        """
        Returns (is_duplicate, reason, dup_of_id).
        """
        # 1. Exact Duplicate Check (SHA-256)
        exact_hash = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        if exact_hash in self.seen_exact_hashes:
            return True, "exact_duplicate", self.seen_exact_hashes[exact_hash]

        # 2. Near-Duplicate Check (MinHash LSH)
        shingles = get_shingles(text, k=5)
        signature = compute_minhash(shingles)

        candidates = set()
        for band_idx in range(NUM_BANDS):
            start = band_idx * ROWS_PER_BAND
            band_key = (band_idx, tuple(signature[start:start + ROWS_PER_BAND]))
            for candidate_id in self.lsh_buckets.get(band_key, []):
                candidates.add(candidate_id)

        # Verify candidate matches with exact Jaccard similarity
        for cand_id in candidates:
            cand_shingles = self.doc_shingles.get(cand_id, set())
            similarity = jaccard_similarity(shingles, cand_shingles)
            if similarity >= self.threshold:
                return True, "near_duplicate", cand_id

        # Document is unique: record into index
        self.seen_exact_hashes[exact_hash] = doc_id
        self.doc_shingles[doc_id] = shingles
        for band_idx in range(NUM_BANDS):
            start = band_idx * ROWS_PER_BAND
            band_key = (band_idx, tuple(signature[start:start + ROWS_PER_BAND]))
            self.lsh_buckets.setdefault(band_key, []).append(doc_id)

        return False, "", ""

    def process_document(self, doc: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """
        Pipeline step wrapper:
        Returns (kept_doc, None) or (None, drop_record).
        """
        doc_id = doc.get("id", "unknown")
        text = doc.get("text", "")

        is_dup, reason, dup_of = self.check_duplicate(doc_id, text)

        if is_dup:
            drop_record = {
                "id": doc_id,
                "status": "dropped",
                "stage": "dedup",
                "reason": reason,
                "dup_of": dup_of
            }
            return None, drop_record

        return doc, None

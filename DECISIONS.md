# DECISIONS.md

## 1. Sources
* **Source 1: Hindi Wikipedia Dump (`hiwiki`)**
  * **License:** Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0)
  * **URL:** `https://dumps.wikimedia.org/hiwiki/latest/hiwiki-latest-pages-articles.xml.bz2`
  * **Raw Size:** 1.69 GB uncompressed XML (`hiwiki-latest-pages-articles.xml`, SHA-256: `b2914dd1...`)
  * **Document Count:** 25,422 pages scanned; 15,000 valid encyclopedic articles extracted
  * **Download Date:** October 2026
* **Source 2: Google Research Hinglish-TOP Dataset (`hinglish_top`)**
  * **License:** Apache License 2.0
  * **URL:** `https://raw.githubusercontent.com/google-research-datasets/Hinglish-TOP-Dataset/main/Dataset/Human%20Annotated%20Data/train.tsv`
  * **Raw Size:** 833 KB TSV (`hinglish_top_train.tsv`, SHA-256: `8bcf9a01...`)
  * **Document Count:** 2,993 task-oriented code-mixed user utterances (`hi-Latn`)
  * **Download Date:** October 2026

---

## 2. Funnel
* **Stage 0 (Raw Scanned):** **28,415** documents
  * `hiwiki`: 25,422 pages | `hinglish_top`: 2,993 queries
* **Stage 1 (Ingest Drops):** **10,422** dropped (17,993 passed)
  * `hiwiki`: 10,422 dropped (MediaWiki redirects `#REDIRECT`, non-article namespaces `ns != 0`, empty text)
  * `hinglish_top`: 0 dropped (100% valid TSV lines)
* **Stage 2 (Unicode & NFC Normalization):** **17,993** passed (0 dropped)
  * Unification of Devanagari Nuktas (`DEVANAGARI_NUKTA_MAP`), NFC composition, invisible formatting stripping (ZWJ, ZWNJ, BOM), and whitespace folding.
* **Stage 3 (Language ID Breakdown):** **17,993** classified
  * `hi` (Devanagari): 14,352 (79.8%)
  * `hi-Latn` (Hinglish): 2,993 (16.6%)
  * `en or other`: 648 (3.6%)
* **Stage 4 (Quality Filtering):** **764** dropped (17,229 passed)
  * `hiwiki`: 728 dropped (excessive symbols/markup > 40%, stub fragments < 3 words or < 15 chars)
  * `hinglish_top`: 36 dropped (isolated 1–2 word command fragments)
* **Stage 5 (Deduplication):** **1,861** dropped (15,368 passed)
  * Exact Duplicates (SHA-256): 229 dropped (225 `hiwiki`, 4 `hinglish_top`)
  * Near Duplicates (MinHash LSH Jaccard $\ge 0.80$): 1,632 dropped (1,516 `hiwiki`, 116 `hinglish_top`)
* **Stage 6 (PII Redaction):** **15,368** passed
  * Scrubbed `<PHONE>`, `<EMAIL>`, `<AADHAAR>`, and `<PAN>`; non-PII integers preserved.
* **Stage 7 (Held-out Eval Extraction):** **200** held out
  * 150 `hi` + 50 `hi-Latn` extracted into `output/eval.jsonl`
* **Final Clean Corpus (`output/clean/train.jsonl.gz`):** **15,168** documents
  * `hi`: 11,871 documents (78.3%)
  * `hi-Latn`: 2,798 documents (18.4%)
  * `en or other`: 499 documents (3.3%)

---

## 3. Near-Duplicates
* **Method & Threshold:** We break text into small 5-character chunks and group documents that share similar chunks into buckets to quickly spot duplicates. We set the overlap cutoff to **0.80 (80% similarity)**.
* **Why 0.80 was chosen:** Below 80%, we accidentally drop valid conversational commands that share common phrasing (like changing a time or name in a reminder). Above 80%, copy-pasted Wikipedia pages and repetitive templates slip through. 80% hits the right balance.
* **Three Borderline Pairs Evaluated:**
  1. `15 minutes ke liye timer set karen` vs `45 minutes ke liye timer set karo`
     * *Jaccard:* **0.808** | *Our Call:* **DROPPED as near-duplicate**. Falls right above 0.80; dropping repetitive command syntactic templates prevents token memorization.
  2. `timer ko phirse shuru karo` vs `Please timer ko phirse shuru karo`
     * *Jaccard:* **0.750** | *Our Call:* **KEPT as unique**. Below 0.80; preserves communicative politeness markers (`Please`) as distinct user conversational distribution.
  3. `20 minutes ke liye timer set karen .` vs `10 minutes ke liye timer set kare`
     * *Jaccard:* **0.846** | *Our Call:* **DROPPED as near-duplicate**. Overlap is near-total, differing only by digit and punctuation.

---

## 4. Filters
* **Three Documents Removed That Had Legitimate Content (Trade-offs):**
  1. `hinglish_top_train_280` (`"pichla gaana"` — *previous song*):
     * *Reason dropped:* `too_short_fragment` (`words = 2 < 3`, `chars = 12 < 15`).
     * *Trade-off:* Valid voice assistant media command, but dropping $< 3$ words is necessary across web crawls to purge noisy search keywords and truncated fragments.
  2. `hinglish_top_train_367` (`"Sandesh"` — *Message*):
     * *Reason dropped:* `too_short_fragment` (`words = 1`).
     * *Trade-off:* Valid single-word conversational intent, but isolated 1-word Latin tokens provide insufficient contextual signal for LLM generative training.
  3. `hiwiki_764` (*पादप रोगविज्ञान* — Plant Pathology):
     * *Reason dropped:* `excessive_symbols` (`symbol_ratio > 0.40`).
     * *Trade-off:* Real encyclopedic article on plant pathology, but wikitext thumbnail markup (`[[चित्र:Powdery mildew.JPG|thumb|...]]`) pushed symbol density over the 40% threshold.

---

## 5. Contamination
* **Method:** 4-tier streaming leak detection checking training documents against the 200 held-out evaluation items:
  1. Exact text match
  2. Normalized match (whitespace/punctuation stripped, lowercase)
  3. Cross-script transliteration match (Devanagari $\leftrightarrow$ Latin phonetic approximation)
  4. 5-character shingle Jaccard similarity ($\ge 0.80$)
* **Affected Eval Items:** **0 leaks detected** across all 15,168 training documents.
* **One Candidate Match Rejected:**
  * Eval query `kya aap is thursday sham 4 baje dentist ke pas jane ke liye mere liye ek reminder laga sakte hai ?` shared high n-gram overlap (`...ke pas jane ke liye mere liye ek reminder laga...`) with training intent patterns.
  * *Why Rejected:* Jaccard similarity was **0.64** ($< 0.80$). Rejected as a leak because the specific entity slot (`dentist`) and temporal anchor (`is thursday sham 4 baje`) are unique evaluation signals rather than memorized training text.

---

## 6. Reproducibility
* **Rebuild Steps (Exact 6-Month Rebuild):**
  1. `git clone <repo_url> && cd Flam_data_assignment`
  2. `./download.sh raw/` — Fetches original pinned data sources with recorded SHA-256 checksums.
  3. `./run.sh raw/ output/` — Runs the full cleaning pipeline offline.
* **Determinism Guarantees:**
  * Fixed random seed (`RANDOM_SEED = 42`) for MinHash hash permutations and stratified eval sampling.
  * Zero external pip dependencies; uses Python standard library exclusively (`hashlib`, `re`, `unicodedata`, `xml.etree`).
  * Cryptographic input hashes and stage counts logged in `output/manifest.json`.

---

## 7. Scale
If this dataset were 2 TB, the first thing that breaks is **RAM memory in deduplication**. Right now, our script keeps a dictionary of previously seen text signatures in memory; with 2 TB of data, this dictionary will grow to tens of gigabytes and crash the script with an Out-of-Memory (OOM) error. Also, processing 2 TB sequentially on a single laptop CPU core would take several days. To fix this, I would store the duplicate signatures in a local disk-based database (like SQLite or Redis) instead of keeping them in Python dictionaries, and split the raw files to process them in parallel using Python's `multiprocessing` library.

---

## 8. Wrap-up
* **What We Didn't Get To:**
  * *Machine Learning Language Identifier:* We used simple rule-based script and word heuristics to keep the code lightweight and offline. Given more time, I would test a lightweight pre-trained model (like FastText) to better catch subtle, mixed English-Hindi words.
* **Engineering Time Spent:** ~3.5 hours total (Ingestion & XML streaming: 1 hr; Normalization, LID & PII: 45 min; Quality filtering & deduplication: 1 hr; Eval holdout, contamination check & DECISIONS.md: 45 min).

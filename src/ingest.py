import bz2
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Generator, Tuple, Optional, Dict, Any

# Prevent field overflow error on unusually large CSV cells
csv.field_size_limit(sys.maxsize)
WIKI_NAMESPACE = "{http://www.mediawiki.org/xml/export-0.11/}"

class StreamingIngestor:
    """
    Format-agnostic streaming ingestor for Stage 1.
    Natively streams raw .xml, .xml.bz2, .tsv, .jsonl, .csv, and .txt files.
    Emits (document, None) for kept records, or (None, drop_record) for skipped/malformed records.
    """

    def __init__(self, max_wiki_docs: Optional[int] = 15000):
        self.max_wiki_docs = max_wiki_docs
        self.total_scanned = 0
        self.total_yielded = 0
        self.total_skipped = 0

    def ingest_directory(self, raw_dir: str) -> Generator[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]], None, None]:
        """
        Scans raw_dir for supported files and yields:
          - (valid_document, None) if record is valid
          - (None, ledger_drop_entry) if record is malformed or skipped
        """
        if not os.path.exists(raw_dir):
            raise FileNotFoundError(f"Input directory does not exist: {raw_dir}")

        supported_exts = (".xml", ".bz2", ".tsv", ".jsonl", ".csv", ".txt")
        files = [
            os.path.join(raw_dir, f) for f in sorted(os.listdir(raw_dir))
            if any(f.endswith(ext) for ext in supported_exts) and not f.startswith(".")
        ]

        if not files:
            raise ValueError(f"No supported data files found in {raw_dir}")

        for file_path in files:
            yield from self.ingest_file(file_path)

    def ingest_file(self, file_path: str) -> Generator[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]], None, None]:
        """
        Dispatches file to the appropriate streaming parser based on extension.
        """
        filename = os.path.basename(file_path)
        source = os.path.splitext(filename)[0].replace(".tar", "")

        if filename.endswith((".xml", ".xml.bz2")):
            yield from self._stream_wiki_xml(file_path, "hiwiki")
        elif filename.endswith(".tsv"):
            yield from self._stream_tsv_csv(file_path, source, delimiter="\t")
        elif filename.endswith(".csv"):
            yield from self._stream_tsv_csv(file_path, source, delimiter=",")
        elif filename.endswith(".jsonl"):
            yield from self._stream_jsonl(file_path, source)
        elif filename.endswith(".txt"):
            yield from self._stream_txt(file_path, source)

    def _stream_wiki_xml(self, file_path: str, source: str):
        """
        Streams MediaWiki XML exports in constant RAM.
        Filters for ns==0 (encyclopedia articles) and drops redirects.
        """
        open_fn = bz2.open if file_path.endswith(".bz2") else open
        wiki_count = 0

        with open_fn(file_path, "rb") as xml_file:
            context = ET.iterparse(xml_file, events=("end",))
            for event, elem in context:
                tag = elem.tag.replace(WIKI_NAMESPACE, "")
                if tag == "page":
                    self.total_scanned += 1
                    ns_elem = elem.find(f"{WIKI_NAMESPACE}ns")
                    title_elem = elem.find(f"{WIKI_NAMESPACE}title")
                    id_elem = elem.find(f"{WIKI_NAMESPACE}id")
                    text_elem = elem.find(f".//{WIKI_NAMESPACE}text")
                    redirect_elem = elem.find(f"{WIKI_NAMESPACE}redirect")

                    if ns_elem is not None and ns_elem.text == "0" and redirect_elem is None:
                        title = title_elem.text if title_elem is not None else ""
                        page_id = id_elem.text if id_elem is not None else str(wiki_count)
                        text = text_elem.text if (text_elem is not None and text_elem.text) else ""

                        if text.strip():
                            wiki_count += 1
                            self.total_yielded += 1
                            yield ({
                                "id": f"hiwiki_{page_id}",
                                "text": text,
                                "source": source,
                                "raw_meta": {"title": title}
                            }, None)

                            if self.max_wiki_docs and wiki_count >= self.max_wiki_docs:
                                elem.clear()
                                break
                        else:
                            self.total_skipped += 1
                            yield (None, self._make_drop_record(f"hiwiki_{page_id}", "empty_article_text"))
                    else:
                        self.total_skipped += 1
                        page_id = id_elem.text if id_elem is not None else f"meta_{self.total_scanned}"
                        yield (None, self._make_drop_record(f"hiwiki_{page_id}", "non_article_or_redirect"))

                    elem.clear()

    def _stream_tsv_csv(self, file_path: str, source: str, delimiter: str):
        """
        Streams TSV or CSV row-by-row. Tolerates corrupted rows and extra quotes.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row_no, row in enumerate(reader, start=1):
                self.total_scanned += 1
                try:
                    text = self._extract_text(row)
                    if not text:
                        self.total_skipped += 1
                        yield (None, self._make_drop_record(f"{source}_{row_no}", "empty_text_column"))
                        continue

                    self.total_yielded += 1
                    yield ({
                        "id": f"{source}_{row_no}",
                        "text": text,
                        "source": source,
                        "raw_meta": row
                    }, None)
                except Exception as err:
                    self.total_skipped += 1
                    yield (None, self._make_drop_record(f"{source}_{row_no}", f"parse_error_{type(err).__name__}"))

    def _stream_jsonl(self, file_path: str, source: str):
        """
        Streams JSON Lines. Survives broken JSON syntax and missing text keys.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                self.total_scanned += 1
                line = line.strip()
                if not line:
                    self.total_skipped += 1
                    yield (None, self._make_drop_record(f"{source}_{line_no}", "empty_line"))
                    continue
                try:
                    data = json.loads(line)
                    text = self._extract_text(data)
                    if not text:
                        self.total_skipped += 1
                        yield (None, self._make_drop_record(f"{source}_{line_no}", "empty_text"))
                        continue
                    self.total_yielded += 1
                    yield ({
                        "id": str(data.get("id") or f"{source}_{line_no}"),
                        "text": text,
                        "source": source,
                        "raw_meta": data
                    }, None)
                except json.JSONDecodeError:
                    self.total_skipped += 1
                    yield (None, self._make_drop_record(f"{source}_{line_no}", "malformed_json"))

    def _stream_txt(self, file_path: str, source: str):
        """
        Streams plain text files line-by-line as individual documents.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                self.total_scanned += 1
                text = line.strip()
                if not text:
                    self.total_skipped += 1
                    yield (None, self._make_drop_record(f"{source}_{line_no}", "empty_line"))
                    continue
                self.total_yielded += 1
                yield ({
                    "id": f"{source}_{line_no}",
                    "text": text,
                    "source": source,
                    "raw_meta": {}
                }, None)

    def _extract_text(self, record: Dict[str, Any]) -> str:
        """
        Polymorphic column extractor. Checks common field names dynamically.
        """
        for key in ("cs_query", "text", "content", "sentence", "body", "query"):
            val = record.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    def _make_drop_record(self, doc_id: str, reason: str) -> Dict[str, str]:
        """
        Standardized ledger entry for dropped records at the ingest stage.
        """
        return {
            "id": doc_id,
            "status": "dropped",
            "stage": "ingest",
            "reason": reason,
            "dup_of": ""
        }

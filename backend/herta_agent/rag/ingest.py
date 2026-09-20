"""Read one allowlisted document and split deterministically without crossing evidence units."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from herta_agent.rag.errors import RagError
from herta_agent.rag.models import Chunk, SourceManifest

CHUNKER_VERSION = "paragraph-600-overlap80-v1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Corpus:
    text: str
    raw_sha256: str
    normalized_sha256: str
    sources_sha256: str
    chunks: tuple[Chunk, ...]

    @property
    def fingerprint(self) -> str:
        return digest(
            f"{self.raw_sha256}:{self.normalized_sha256}:{self.sources_sha256}"
            f":{CHUNKER_VERSION}".encode()
        )


def _spans(text: str, start: int, end: int):
    # Paragraph boundaries preserve complete short units. Only long paragraphs overlap.
    for paragraph in re.finditer(r"\S.*?(?=\n[ \t]*\n|\Z)", text[start:end], re.S):
        left = start + paragraph.start()
        right = left + len(paragraph[0].rstrip())
        while left < right:
            stop = min(left + 600, right)
            if stop < right:
                boundaries = list(re.finditer(r"[。！？.!?；;]\s*", text[left:stop]))
                if boundaries and boundaries[-1].end() >= 300:
                    stop = left + boundaries[-1].end()
            # Keep exact source offsets, including internal line breaks.
            yield left, stop
            if stop == right:
                break
            left = stop - 80


def load_corpus(root: Path) -> Corpus:
    try:
        root = root.resolve(strict=True)
        metadata_path = root / "sources.json"
        if metadata_path.resolve().parent != root:
            raise ValueError("Manifest outside knowledge directory")
        metadata = metadata_path.read_bytes()
        manifest = SourceManifest.model_validate_json(metadata)
        if manifest.document != "herta.md":
            raise ValueError("Only herta.md is allowlisted")
        path = root / manifest.document
        if path.resolve().parent != root:
            raise ValueError("Document outside knowledge directory")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip() or "\x00" in text:
            raise ValueError("Empty or invalid corpus")
        normalized_hash = digest(text.encode("utf-8"))
        headings = list(re.finditer(r"^## (K\d{2}) ([^\n]+)$", text, re.M))
        units = {unit.id: unit for unit in manifest.units}
        ids = [match[1] for match in headings]
        if (
            not headings
            or len(units) != len(manifest.units)
            or len(set(ids)) != len(ids)
            or set(ids) != set(units)
        ):
            raise ValueError("Missing, duplicate or unknown evidence units")
        # Do not silently swallow malformed section headers into another unit.
        if len(re.findall(r"^##\s", text, re.M)) != len(headings):
            raise ValueError("Invalid section header")
        chunks = []
        for i, heading in enumerate(headings):
            unit = units[heading[1]]
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            spans = list(_spans(text, heading.end(), end))
            if not spans:
                raise ValueError("Empty evidence unit")
            for left, right in spans:
                identity = digest(f"{normalized_hash}:{unit.id}:{left}:{right}".encode())[:16]
                chunks.append(
                    Chunk(
                        id=f"{unit.id}-{identity}",
                        unit_id=unit.id,
                        title=heading[2].strip(),
                        text=text[left:right],
                        document=manifest.document,
                        document_sha256=normalized_hash,
                        start=left,
                        end=right,
                        line_start=text.count("\n", 0, left) + 1,
                        line_end=text.count("\n", 0, right - 1) + 1,
                        source=manifest.source,
                        source_spans=unit.source_spans,
                    )
                )
        return Corpus(text, digest(raw), normalized_hash, digest(metadata), tuple(chunks))
    except (OSError, UnicodeError, ValidationError, ValueError):
        raise RagError(
            "corpus_invalid", "知识文本或来源清单无效，请检查白名单、编号和内容。"
        ) from None

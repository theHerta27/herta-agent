"""Immutable index versions, published by replacing a small same-volume pointer."""

import io
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import Field, ValidationError

from herta_agent.rag.errors import RagError
from herta_agent.rag.ingest import CHUNKER_VERSION, Corpus, digest
from herta_agent.rag.models import Chunk, Record


class IndexManifest(Record):
    schema_version: int = Field(strict=True, ge=1, le=1)
    index_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_model: str = Field(min_length=1)
    chunker: str
    dimension: int = Field(strict=True, gt=0)
    count: int = Field(strict=True, gt=0)
    vectors_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class IndexSnapshot:
    manifest: IndexManifest
    chunks: tuple[Chunk, ...]
    vectors: np.ndarray

    @property
    def index_id(self) -> str:
        return self.manifest.index_id


def normalized_vectors(values, *, count: int, dimension: int | None = None) -> np.ndarray:
    try:
        # Validate before conversion: bools/strings must not silently become numbers.
        if isinstance(values, np.ndarray):
            if values.dtype.kind not in "fiu":
                raise ValueError("Non numeric array")
        else:
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float))
                for row in values
                for v in row
            ):
                raise ValueError("Non numeric vector")
        array = np.asarray(values, dtype=np.float64)
        if (
            array.ndim != 2
            or array.shape[0] != count
            or array.shape[1] == 0
            or (dimension is not None and array.shape[1] != dimension)
            or not np.isfinite(array).all()
        ):
            raise ValueError("Shape or finite value mismatch")
        # Scale first so valid extreme magnitudes do not overflow the norm.
        scale = np.max(np.abs(array), axis=1, keepdims=True)
        if np.any(scale == 0):
            raise ValueError("Zero vector")
        scaled = array / scale
        normalized = (scaled / np.linalg.norm(scaled, axis=1, keepdims=True)).astype(np.float32)
        normalized.setflags(write=False)
        return normalized
    except (ValueError, TypeError, OverflowError):
        raise RagError("index_vectors", "向量数量、维度或数值无效。") from None


def _read_version(directory: Path, corpus: Corpus, fingerprint: str) -> IndexSnapshot:
    for name in ("chunks.jsonl", "vectors.npy", "manifest.json"):
        if (directory / name).resolve().parent != directory.resolve():
            raise ValueError("Index file escapes version directory")
    manifest = IndexManifest.model_validate_json((directory / "manifest.json").read_bytes())
    if (
        manifest.corpus_fingerprint != corpus.fingerprint
        or manifest.embedding_fingerprint != fingerprint
        or manifest.chunker != CHUNKER_VERSION
    ):
        raise RagError("index_mismatch", "索引与当前知识或 Embedding 配置不匹配，请重新建库。")
    if (
        manifest.index_id != directory.name
        or manifest.raw_sha256 != corpus.raw_sha256
        or manifest.normalized_sha256 != corpus.normalized_sha256
        or manifest.sources_sha256 != corpus.sources_sha256
    ):
        raise ValueError("Manifest metadata mismatch")
    chunk_bytes = (directory / "chunks.jsonl").read_bytes()
    vector_bytes = (directory / "vectors.npy").read_bytes()
    if (
        digest(chunk_bytes) != manifest.chunks_sha256
        or digest(vector_bytes) != manifest.vectors_sha256
    ):
        raise ValueError("Index checksum mismatch")
    chunks = tuple(Chunk.model_validate_json(line) for line in chunk_bytes.splitlines())
    if chunks != corpus.chunks or len(chunks) != manifest.count:
        raise ValueError("Chunk mapping mismatch")
    # No pickle or mmap; keep a private, read-only snapshot for this process.
    if not vector_bytes.startswith(b"\x93NUMPY"):
        raise ValueError("Expected NPY array")
    vectors = np.load(io.BytesIO(vector_bytes), allow_pickle=False)
    if vectors.dtype != np.float32:
        raise ValueError("Expected float32 matrix")
    normalized = normalized_vectors(vectors, count=len(chunks), dimension=manifest.dimension)
    if not np.allclose(vectors, normalized, atol=1e-6):
        raise ValueError("Vectors must be normalized")
    vectors.setflags(write=False)
    return IndexSnapshot(manifest, chunks, vectors)


def load_index(root: Path, corpus: Corpus, fingerprint: str) -> IndexSnapshot:
    if not (root / "current.json").exists():
        raise RagError("index_missing", "尚未建立知识索引，请先运行 RAG build。")
    try:
        pointer = json.loads((root / "current.json").read_bytes())
        index_id = pointer["index_id"]
        if not isinstance(index_id, str) or not re.fullmatch("[0-9a-f]{32}", index_id):
            raise ValueError("Invalid pointer")
        directory = root / index_id
        if directory.resolve().parent != root.resolve():
            raise ValueError("Version escapes index root")
        return _read_version(directory, corpus, fingerprint)
    except (OSError, ValueError, KeyError, TypeError, ValidationError, EOFError):
        raise RagError("index_invalid", "知识索引损坏或不完整，请重新建库。") from None


def publish_index(
    root: Path, corpus: Corpus, vectors, fingerprint: str, model: str
) -> IndexSnapshot:
    matrix = normalized_vectors(vectors, count=len(corpus.chunks))
    try:
        root.mkdir(parents=True, exist_ok=True)
        index_id = uuid.uuid4().hex
        directory = root / index_id
        directory.mkdir()
        chunk_bytes = ("\n".join(c.model_dump_json() for c in corpus.chunks) + "\n").encode("utf-8")
        (directory / "chunks.jsonl").write_bytes(chunk_bytes)
        with (directory / "vectors.npy").open("wb") as stream:
            np.save(stream, matrix, allow_pickle=False)
        manifest = IndexManifest(
            schema_version=1,
            index_id=index_id,
            corpus_fingerprint=corpus.fingerprint,
            raw_sha256=corpus.raw_sha256,
            normalized_sha256=corpus.normalized_sha256,
            sources_sha256=corpus.sources_sha256,
            embedding_fingerprint=fingerprint,
            embedding_model=model,
            chunker=CHUNKER_VERSION,
            dimension=matrix.shape[1],
            count=len(corpus.chunks),
            vectors_sha256=digest((directory / "vectors.npy").read_bytes()),
            chunks_sha256=digest(chunk_bytes),
        )
        (directory / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        snapshot = _read_version(directory, corpus, fingerprint)
        temporary = root / f"current-{index_id}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump({"index_id": index_id}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, root / "current.json")
        finally:
            temporary.unlink(missing_ok=True)
        return snapshot
    except (OSError, ValueError, ValidationError):
        raise RagError("index_publish", "索引发布失败；原 current 指针保持有效。") from None

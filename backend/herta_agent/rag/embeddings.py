"""Independent embedding configuration and one OpenAI-compatible adapter."""

import asyncio
import hashlib
import json
import math
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from herta_agent.rag.errors import RagError


class EmbeddingSettings(BaseModel):
    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", hide_input_in_errors=True, allow_inf_nan=False
    )

    base_url: str
    model: str = Field(min_length=1)
    api_key: SecretStr = Field(exclude=True, repr=False)
    document_prefix: str = ""
    query_prefix: str = ""
    max_input_chars: int = Field(default=16000, ge=1, le=1000000)
    timeout: float = Field(default=60.0, gt=0, le=600)
    batch_size: int = Field(default=32, ge=1, le=2048)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError("Invalid embedding base URL")
        _ = parsed.port
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Embedding model is required")
        return value.strip()

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.strip() or any(ord(c) < 32 or ord(c) > 126 for c in raw):
            raise ValueError("Invalid embedding API key")
        return value

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        """Read credentials only from the local process environment, never chat config."""
        try:
            options = {
                "base_url": os.environ["HERTA_EMBEDDING_BASE_URL"],
                "model": os.environ["HERTA_EMBEDDING_MODEL"],
                "api_key": SecretStr(os.environ["HERTA_EMBEDDING_API_KEY"]),
            }
            for name, parse in [
                ("document_prefix", str),
                ("query_prefix", str),
                ("max_input_chars", int),
                ("timeout", float),
                ("batch_size", int),
            ]:
                raw = os.environ.get("HERTA_EMBEDDING_" + name.upper())
                if raw is not None:
                    options[name] = parse(raw)
            return cls(**options)
        except (KeyError, ValueError, TypeError):
            raise RagError(
                "embedding_config", "Embedding configuration is missing or invalid."
            ) from None

    @property
    def fingerprint(self) -> str:
        encoding = {
            "base_url": self.base_url,
            "model": self.model,
            "document_prefix": self.document_prefix,
            "query_prefix": self.query_prefix,
            "max_input_chars": self.max_input_chars,
        }
        return hashlib.sha256(
            json.dumps(encoding, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()


class Embeddings(Protocol):
    @property
    def fingerprint(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class RemoteEmbeddings:
    def __init__(self, settings: EmbeddingSettings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client  # Caller owns this client and its lifecycle.

    @property
    def fingerprint(self) -> str:
        return self.settings.fingerprint

    @property
    def model(self) -> str:
        return self.settings.model

    def _prepare(self, texts: list[str], prefix: str) -> list[str]:
        if not isinstance(texts, list):
            raise RagError("embedding_input", "Embedding inputs must be a list of text strings.")
        prepared = []
        for text in texts:
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(prefix + text) > self.settings.max_input_chars
            ):
                raise RagError(
                    "embedding_input",
                    "Embedding input is empty, invalid, or exceeds the character limit.",
                )
            prepared.append(prefix + text)
        return prepared

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prepared = self._prepare(texts, self.settings.document_prefix)
        result: list[list[float]] = []
        dimension = None
        for start in range(0, len(prepared), self.settings.batch_size):
            batch = await self._request(prepared[start : start + self.settings.batch_size])
            for vector in batch:
                if dimension is not None and len(vector) != dimension:
                    raise RagError(
                        "embedding_response", "Embedding vector dimensions are inconsistent."
                    )
                dimension = len(vector)
            result.extend(batch)
        return result

    async def embed_query(self, text: str) -> list[float]:
        return (await self._request(self._prepare([text], self.settings.query_prefix)))[0]

    async def _request(self, texts: list[str]) -> list[list[float]]:
        try:
            async with asyncio.timeout(self.settings.timeout):
                response = await self.client.post(
                    self.settings.base_url + "/embeddings",
                    headers={"Authorization": "Bearer " + self.settings.api_key.get_secret_value()},
                    json={"model": self.model, "input": texts, "encoding_format": "float"},
                    timeout=self.settings.timeout,
                    follow_redirects=False,
                )
        except (httpx.TimeoutException, TimeoutError):
            raise RagError("embedding_timeout", "Embedding service timed out.") from None
        except httpx.RequestError:
            raise RagError("embedding_http", "Unable to reach the embedding service.") from None
        if not response.is_success:
            raise RagError(
                "embedding_http", f"Embedding service returned HTTP {response.status_code}."
            )
        try:
            payload = response.json()
            rows = payload["data"]
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise ValueError
            ordered: dict[int, list[float]] = {}
            dimension = None
            for row in rows:
                index = row["index"]
                values = row["embedding"]
                if type(index) is not int or not 0 <= index < len(texts) or index in ordered:
                    raise ValueError
                if not isinstance(values, list) or not values:
                    raise ValueError
                if any(type(v) not in (int, float) for v in values):
                    raise ValueError
                vector = [float(v) for v in values]
                if not all(math.isfinite(v) for v in vector) or not any(v != 0 for v in vector):
                    raise ValueError
                if dimension is not None and len(vector) != dimension:
                    raise ValueError
                dimension = len(vector)
                ordered[index] = vector
            return [ordered[i] for i in range(len(texts))]
        except (ValueError, KeyError, TypeError, OverflowError):
            raise RagError(
                "embedding_response", "Embedding service returned an invalid response."
            ) from None


@lru_cache(maxsize=32)
def _model_digest(path: str, size: int, modified: int) -> str:
    # The size and timestamp invalidate this cache when local weights change.
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


class LocalEmbeddingSettings(BaseModel):
    """Encoding contract for a fully downloaded BGE Chinese BERT snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    model_path: Path
    model: str = "BAAI/bge-large-zh"
    query_prefix: str = "为这个句子生成表示以用于检索相关文章："
    document_prefix: str = ""
    max_input_chars: int = Field(default=16000, ge=1, le=1000000)
    max_tokens: int = Field(default=512, ge=8, le=512)
    batch_size: int = Field(default=4, ge=1, le=64)

    @field_validator("model_path")
    @classmethod
    def validate_path(cls, value: Path) -> Path:
        value = value.expanduser().resolve()
        required = ("config.json", "tokenizer.json", "model.safetensors")
        if not all((value / name).is_file() and (value / name).stat().st_size for name in required):
            raise ValueError("A complete offline model snapshot is required")
        return value

    @property
    def fingerprint(self) -> str:
        files = {}
        for name in ("config.json", "tokenizer.json", "model.safetensors"):
            path = self.model_path / name
            stat = path.stat()
            files[name] = _model_digest(str(path), stat.st_size, stat.st_mtime_ns)
        encoding = {
            "adapter": "local-bge-cls-l2-v1",
            "model": self.model,
            "files": files,
            "query_prefix": self.query_prefix,
            "document_prefix": self.document_prefix,
            "max_tokens": self.max_tokens,
            "max_input_chars": self.max_input_chars,
            "truncation": True,
        }
        return hashlib.sha256(
            json.dumps(encoding, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()


def find_local_model() -> Path | None:
    """Find complete cached BGE weights without contacting Hugging Face."""
    explicit = os.environ.get("HERTA_LOCAL_EMBEDDING_MODEL")
    if explicit is not None:
        return Path(explicit).expanduser()
    try:
        default_cache = Path.home() / ".cache" / "huggingface"
    except RuntimeError:
        return None
    cache = Path(os.environ.get("HF_HOME", str(default_cache)))
    hub = Path(os.environ.get("HUGGINGFACE_HUB_CACHE", str(cache / "hub")))
    snapshots = hub / "models--BAAI--bge-large-zh" / "snapshots"
    if not snapshots.is_dir():
        return None
    for path in sorted(snapshots.iterdir(), reverse=True):
        try:
            return LocalEmbeddingSettings(model_path=path).model_path
        except (ValueError, OSError):
            continue
    return None


class LocalEmbeddings:
    """Lazy CPU BGE inference; all model loading is strictly local and off the event loop."""

    def __init__(self, settings: LocalEmbeddingSettings):
        self.settings = settings
        self._fingerprint = settings.fingerprint
        self._lock = threading.Lock()
        self._runtime = None

    @property
    def model(self) -> str:
        return self.settings.model

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def _prepare(self, texts: list[str], prefix: str) -> list[str]:
        if not isinstance(texts, list) or any(
            not isinstance(text, str)
            or not text.strip()
            or len(prefix + text) > self.settings.max_input_chars
            for text in texts
        ):
            raise RagError("embedding_input", "Embedding input is empty, invalid, or too long.")
        return [prefix + text for text in texts]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prepared = self._prepare(texts, self.settings.document_prefix)
        if not prepared:
            return []
        return await asyncio.to_thread(self._encode, prepared)

    async def embed_query(self, text: str) -> list[float]:
        return (
            await asyncio.to_thread(self._encode, self._prepare([text], self.settings.query_prefix))
        )[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if self._runtime is None:
                try:
                    import torch
                    from transformers import AutoModel, AutoTokenizer
                except ImportError:
                    raise RagError(
                        "embedding_dependency", "Local embedding requires the project local extra."
                    ) from None
                try:
                    torch.set_num_threads(min(4, os.cpu_count() or 1))
                    tokenizer = AutoTokenizer.from_pretrained(
                        str(self.settings.model_path),
                        local_files_only=True,
                        trust_remote_code=False,
                    )
                    model = AutoModel.from_pretrained(
                        str(self.settings.model_path),
                        local_files_only=True,
                        trust_remote_code=False,
                        use_safetensors=True,
                    )
                    if model.config.model_type != "bert":
                        raise ValueError("Local adapter requires a BGE BERT model")
                    model.eval()
                    self._runtime = (torch, tokenizer, model)
                except (OSError, ValueError, RuntimeError):
                    raise RagError(
                        "embedding_config", "Unable to load the offline BGE model."
                    ) from None
            torch, tokenizer, model = self._runtime
            vectors = []
            try:
                with torch.inference_mode():
                    for start in range(0, len(texts), self.settings.batch_size):
                        inputs = tokenizer(
                            texts[start : start + self.settings.batch_size],
                            padding=True,
                            truncation=True,
                            max_length=self.settings.max_tokens,
                            return_tensors="pt",
                        )
                        encoded = model(**inputs).last_hidden_state[:, 0]
                        encoded = torch.nn.functional.normalize(encoded, p=2, dim=1)
                        if not torch.isfinite(encoded).all():
                            raise ValueError("Invalid local embedding")
                        vectors.extend(encoded.tolist())
            except (ValueError, RuntimeError):
                raise RagError(
                    "embedding_response", "Offline embedding inference failed."
                ) from None
            return vectors


def create_embeddings(client: httpx.AsyncClient) -> Embeddings:
    """Explicit remote configuration wins; otherwise use complete local weights."""
    provider = os.environ.get("HERTA_EMBEDDING_PROVIDER", "auto").lower().strip()
    if provider not in {"auto", "remote", "local"}:
        raise RagError("embedding_config", "Embedding provider must be auto, local, or remote.")
    remote_configured = any(
        bool(os.environ.get(name, "").strip())
        for name in ("HERTA_EMBEDDING_BASE_URL", "HERTA_EMBEDDING_MODEL", "HERTA_EMBEDDING_API_KEY")
    )
    if provider == "remote" or (provider == "auto" and remote_configured):
        return RemoteEmbeddings(EmbeddingSettings.from_env(), client)
    path = find_local_model()
    if path is None:
        raise RagError(
            "embedding_config", "No complete local embedding model or remote settings found."
        )
    try:
        return LocalEmbeddings(LocalEmbeddingSettings(model_path=path))
    except (ValueError, OSError):
        raise RagError(
            "embedding_config", "A complete offline BGE model snapshot is required."
        ) from None

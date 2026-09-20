"""Independent embedding configuration and one OpenAI-compatible adapter."""

import asyncio
import hashlib
import json
import math
import os
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

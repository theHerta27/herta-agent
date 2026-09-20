"""Persisted evidence metadata; offsets refer to normalized source text."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Source(Record):
    file: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    url: str = Field(pattern=r"^https?://")
    retrieved_at: str | None
    reviewed_at: str
    note: str


class Unit(Record):
    id: str = Field(pattern=r"^K\d{2}$")
    source_spans: tuple[tuple[StrictInt, StrictInt], ...] = Field(min_length=1)
    section: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_spans(self):
        if any(start < 1 or end < start for start, end in self.source_spans):
            raise ValueError("Invalid original source line spans")
        return self


class SourceManifest(Record):
    schema_version: int = Field(strict=True, ge=1, le=1)
    corpus_id: str = Field(min_length=1)
    document: str
    content_kind: str
    source: Source
    units: tuple[Unit, ...] = Field(min_length=1)


class Chunk(Record):
    id: str = Field(pattern=r"^K\d{2}-[0-9a-f]{16}$")
    unit_id: str = Field(pattern=r"^K\d{2}$")
    title: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=600)
    document: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: int = Field(strict=True, ge=0)
    end: int = Field(strict=True, gt=0)
    line_start: int = Field(strict=True, ge=1)
    line_end: int = Field(strict=True, ge=1)
    source: Source
    source_spans: tuple[tuple[StrictInt, StrictInt], ...]

    @model_validator(mode="after")
    def valid_offsets(self):
        if self.end - self.start != len(self.text) or self.line_end < self.line_start:
            raise ValueError("Invalid chunk offsets")
        return self

    @property
    def embedding_text(self) -> str:
        return f"{self.title}\n{self.text}"

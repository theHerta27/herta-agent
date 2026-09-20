"""Exact cosine ranking followed by explicit, inspectable evidence selection."""

from pydantic import Field

from herta_agent.rag.embeddings import Embeddings
from herta_agent.rag.errors import RagError
from herta_agent.rag.models import Record
from herta_agent.rag.store import IndexSnapshot, normalized_vectors


class SearchSettings(Record):
    k: int = Field(default=4, strict=True, ge=1, le=20)
    min_score: float = Field(default=0.0, strict=True, ge=-1, le=1)
    max_chars: int = Field(default=2400, strict=True, ge=1, le=2400)


class Retriever:
    def __init__(
        self, index: IndexSnapshot, embeddings: Embeddings, settings: SearchSettings | None = None
    ):
        if index.manifest.embedding_fingerprint != embeddings.fingerprint:
            raise RagError("index_mismatch", "查询编码配置与索引不匹配，请重新建库。")
        self.index, self.embeddings = index, embeddings
        self.settings = settings or SearchSettings()

    async def search(self, query: str) -> dict:
        report = await self.inspect(query)
        del report["candidates"]
        return report

    async def inspect(self, query: str) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query.strip()) > 1000:
            raise RagError("query_invalid", "查询须为 1–1000 字符的非空文本。")
        query = query.strip()
        vector = await self.embeddings.embed_query(query)
        normalized = normalized_vectors([vector], count=1, dimension=self.index.manifest.dimension)
        scores = self.index.vectors @ normalized[0]
        # float32 rounding can exceed the mathematical [-1,1] interval slightly.
        ranking = sorted(
            range(len(scores)), key=lambda i: (-float(scores[i]), self.index.chunks[i].id)
        )
        selected, candidates = [], []
        used = 0
        for row in ranking:
            chunk = self.index.chunks[row]
            score = max(-1.0, min(1.0, float(scores[row])))
            reason = "selected"
            if score < self.settings.min_score:
                reason = "below_threshold"
            elif any(
                other["unit_id"] == chunk.unit_id
                and other["start"] < chunk.end
                and chunk.start < other["end"]
                for other in selected
            ):
                reason = "overlap"
            elif len(selected) >= self.settings.k:
                reason = "limit"
            elif used + len(chunk.text) > self.settings.max_chars:
                reason = "budget"
            evidence = {**chunk.model_dump(mode="json"), "score": score}
            candidates.append({**evidence, "reason": reason})
            if reason == "selected":
                selected.append(evidence)
                used += len(chunk.text)
        return {
            "query": query,
            "index_id": self.index.index_id,
            "method": "exact_cosine",
            "settings": self.settings.model_dump(),
            "chunks": selected,
            "reason": "evidence_returned" if selected else "no_relevant_evidence",
            "candidates": candidates,
        }

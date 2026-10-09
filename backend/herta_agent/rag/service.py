"""Composition helpers used by entry points; the Runtime knows nothing about RAG."""

from pathlib import Path

import httpx

from herta_agent.rag.embeddings import create_embeddings
from herta_agent.rag.ingest import load_corpus
from herta_agent.rag.retriever import Retriever, SearchSettings
from herta_agent.rag.store import load_index

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE = PROJECT_ROOT / "knowledge"
DEFAULT_INDEX = PROJECT_ROOT / ".local" / "rag"
DEFAULT_QUESTIONS = PROJECT_ROOT / "evals" / "rag" / "questions.jsonl"


def load_retriever(
    client: httpx.AsyncClient,
    knowledge: Path = DEFAULT_KNOWLEDGE,
    index_root: Path = DEFAULT_INDEX,
    settings: SearchSettings | None = None,
) -> Retriever:
    embeddings = create_embeddings(client)
    corpus = load_corpus(knowledge)
    index = load_index(index_root, corpus, embeddings.fingerprint)
    return Retriever(index, embeddings, settings)

"""Safe first-launch checks; explicit prepare builds a versioned knowledge index."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from herta_agent.config import ProviderSettings
from herta_agent.rag.embeddings import create_embeddings
from herta_agent.rag.errors import RagError
from herta_agent.rag.ingest import load_corpus
from herta_agent.rag.store import load_index, publish_index
from herta_agent.runtime.errors import AgentError
from herta_agent.service.settings import ServiceSettings


async def ensure_index(embeddings, knowledge: Path, index_root: Path, *, prepare=False):
    corpus = load_corpus(knowledge)
    try:
        index = load_index(index_root, corpus, embeddings.fingerprint)
    except RagError as error:
        if not prepare:
            return {"index_ready": False, "index_built": False, "error_code": error.code}
        vectors = await embeddings.embed_documents([c.embedding_text for c in corpus.chunks])
        index = publish_index(index_root, corpus, vectors, embeddings.fingerprint, embeddings.model)
        built = True
    else:
        built = False
    return {
        "index_ready": True,
        "index_built": built,
        "index_id": index.index_id,
        "embedding_model": embeddings.model,
        "dimension": index.manifest.dimension,
        "chunks": len(index.chunks),
    }


async def inspect(*, prepare=False, offline=False):
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "chat_configured": False,
        "index_ready": False,
        "index_built": False,
    }
    try:
        config = ProviderSettings.from_env()
        report.update(chat_configured=True, chat_model=config.model)
    except AgentError:
        report["chat_error"] = "chat_not_configured"
    settings = ServiceSettings.from_env()
    async with httpx.AsyncClient() as client:
        try:
            embeddings = create_embeddings(client)
            if offline and type(embeddings).__name__ != "LocalEmbeddings":
                report["rag_error"] = "remote_embeddings_disabled"
                return report
            report["embedding_provider"] = (
                "local" if type(embeddings).__name__ == "LocalEmbeddings" else "remote"
            )
            report.update(
                await ensure_index(
                    embeddings, settings.knowledge_path, settings.index_path, prepare=prepare
                )
            )
        except RagError as error:
            report["rag_error"] = error.code
    return report


def main():
    parser = argparse.ArgumentParser(description="Prepare Herta without exposing credentials")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = asyncio.run(inspect(prepare=args.prepare, offline=args.offline))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(json.dumps(report, ensure_ascii=True))
    except (AgentError, ValueError, OSError):
        print('{"error":"startup_configuration_invalid"}')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

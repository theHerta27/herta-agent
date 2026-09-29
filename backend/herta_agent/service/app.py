"""Local HTTP composition. Runtime and storage remain independent of FastAPI."""

from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from herta_agent.coding import CodeContextBuilder, CodingSettings
from herta_agent.config import ProviderSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.persona import PersonaContextBuilder
from herta_agent.rag.errors import RagError
from herta_agent.rag.service import load_retriever
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import AgentError, ToolExecutionError
from herta_agent.service.review_mode import review_registry
from herta_agent.service.runs import RunCapacityError, RunManager, SessionConflictError
from herta_agent.service.schemas import EmptyRequest, RunInput
from herta_agent.service.settings import ServiceSettings
from herta_agent.service.sse import RunResponse
from herta_agent.storage.models import StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore
from herta_agent.tools.coding import coding_registry
from herta_agent.tools.coding.sandbox import check_docker
from herta_agent.tools.coding.workspace import Workspace
from herta_agent.tools.echo import echo_registry
from herta_agent.tools.search_knowledge import search_knowledge_spec


def error_response(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(settings: ServiceSettings, *, provider=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        store = SQLiteSessionStore(settings.db_path)
        app.state.store, app.state.manager = store, None
        app.state.rag_available = False
        app.state.test_runner_available = False
        app.state.test_runner_error = None
        clients = []
        try:
            await store.open()
            await store.recover_interrupted()
            selected = provider
            coding = CodingSettings.from_env()
            if coding:
                workspace = Workspace.open(coding.root)
                coding = replace(coding, root=workspace.root)
                registry = (
                    review_registry(workspace)
                    if coding.mode == "review"
                    else coding_registry(workspace, writable=True)
                )
                if coding.mode == "coding":
                    try:
                        await check_docker()
                    except ToolExecutionError as error:
                        app.state.test_runner_error = error.code
                    else:
                        app.state.test_runner_available = True
            else:
                registry = echo_registry()
            unavailable = RagError("index_missing", "知识检索未配置。")
            if selected is None and settings.provider == "demo":
                selected = DemoProvider()
            elif selected is None:
                try:
                    config = ProviderSettings.from_env()
                except AgentError:
                    config = None
                if config is not None:
                    chat_client = httpx.AsyncClient(
                        timeout=httpx.Timeout(settings.run.request_timeout, connect=10)
                    )
                    clients.append(chat_client)
                    selected = OpenAICompatibleProvider(config, chat_client)
                    if coding is None:
                        embedding_client = httpx.AsyncClient()
                        clients.append(embedding_client)
                        try:
                            retriever = load_retriever(
                                embedding_client, settings.knowledge_path, settings.index_path
                            )
                        except RagError as error:
                            unavailable = error
                        else:
                            registry.register(search_knowledge_spec(retriever))
                            app.state.rag_available = True
            if coding is None and not app.state.rag_available:
                registry.register(search_knowledge_spec(unavailable=unavailable))
            if selected is not None:
                agent = Agent(
                    selected,
                    settings.run,
                    registry=registry,
                    context_builder=(
                        CodeContextBuilder(coding)
                        if coding
                        else PersonaContextBuilder(settings.soul_path)
                    ),
                    streaming=callable(getattr(selected, "stream", None)),
                )
                app.state.manager = RunManager(store, agent, settings)
            yield
        finally:
            # A shutdown timeout must not close clients underneath a still-owned Run.
            if app.state.manager is not None:
                await app.state.manager.shutdown()
            else:
                await store.close()
            for client in reversed(clients):
                await client.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return error_response(422, "invalid_request", "请求字段或参数无效。")

    @app.exception_handler(StoreError)
    async def store_error(request, error):
        status = 404 if error.code == "store_not_found" else 503
        return error_response(status, error.code, str(error))

    @app.exception_handler(SessionConflictError)
    async def conflict(request, error):
        return error_response(409, error.code, str(error))

    @app.exception_handler(RunCapacityError)
    async def capacity(request, error):
        return error_response(429, error.code, str(error))

    @app.get("/health")
    async def health():
        manager = app.state.manager
        return {
            "storage_writable": app.state.store.writable,
            "chat_available": manager is not None,
            "rag_available": app.state.rag_available,
            "test_runner_available": app.state.test_runner_available,
            "test_runner_error": app.state.test_runner_error,
            "active_runs": manager.active_count if manager else 0,
        }

    @app.post("/sessions", status_code=201)
    async def create_session(body: EmptyRequest | None = None):
        return await app.state.store.create_session()

    @app.get("/sessions")
    async def list_sessions(
        after_id: str | None = Query(None, min_length=1, max_length=256),
        limit: int = Query(50, ge=1, le=100),
    ):
        return await app.state.store.list_sessions(after_id=after_id, limit=limit)

    @app.get("/sessions/{session_id}")
    async def get_session(
        session_id: str, after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)
    ):
        session = await app.state.store.get_session(session_id)
        history = await app.state.store.load_history(session_id)
        return {
            "session": session,
            "messages": [r for r in history if r.seq > after_seq][:limit],
            "current_run": await app.state.store.get_run(history[-1].run_id) if history else None,
        }

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str):
        if app.state.manager is not None:
            return await app.state.manager.get(run_id)
        return {"run": await app.state.store.get_run(run_id), "cancel_requested": False}

    @app.post("/runs/{run_id}/cancel")
    async def cancel(run_id: str, body: EmptyRequest | None = None):
        if app.state.manager is None:
            run = await app.state.store.get_run(run_id)
            return {"accepted": False, "status": run.status, "cancel_requested": False}
        return await app.state.manager.cancel(run_id, "user")

    @app.post("/sessions/{session_id}/runs")
    async def submit(session_id: str, body: RunInput, request: Request):
        if "last-event-id" in request.headers:
            return JSONResponse(
                {
                    "error": {
                        "code": "replay_unsupported",
                        "message": "不支持SSE重放；请读取Run状态。",
                    }
                },
                status_code=400,
            )
        await app.state.store.get_session(session_id)
        if app.state.manager is None:
            raise StoreError("chat_unavailable", "聊天模型未配置。")
        app.state.manager.check_admission(session_id)
        return RunResponse(app.state.manager, session_id, body.text, settings)

    return app

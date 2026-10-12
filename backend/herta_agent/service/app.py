"""Local HTTP composition. Runtime and storage remain independent of FastAPI."""

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from herta_agent.companion.context import CompanionContext
from herta_agent.companion.router import companion_router, scheduler, stop_scheduler
from herta_agent.companion.speech_router import speech_router
from herta_agent.companion.store import CompanionStore
from herta_agent.companion.tools import companion_tools
from herta_agent.config import ProviderSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.persona import PersonaContextBuilder
from herta_agent.productivity.router import productivity_router
from herta_agent.productivity.tools import productivity_tools
from herta_agent.rag.errors import RagError
from herta_agent.rag.service import load_retriever
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import AgentError
from herta_agent.service.runs import RunCapacityError, RunManager, SessionConflictError
from herta_agent.service.schemas import EmptyRequest, RunInput
from herta_agent.service.settings import ServiceSettings
from herta_agent.service.sse import RunResponse
from herta_agent.storage.models import StoreError
from herta_agent.storage.sqlite import SQLiteSessionStore
from herta_agent.tools.echo import echo_registry
from herta_agent.tools.search_knowledge import search_knowledge_spec
from herta_agent.workspace.paths import WorkspaceError
from herta_agent.workspace.router import workspace_router
from herta_agent.workspace.service import WorkspaceService
from herta_agent.workspace.tools import workspace_tools


def error_response(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(settings: ServiceSettings, *, provider=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        store = SQLiteSessionStore(settings.db_path)
        app.state.store, app.state.manager = store, None
        app.state.rag_available = False
        app.state.embedding_provider = None
        app.state.embedding_model = None
        app.state.mcp_available = False
        app.state.mcp_error = None
        app.state.companion = CompanionStore(settings.db_path.with_name("companionship.sqlite3"))
        app.state.workspace = WorkspaceService(settings.db_path.with_name("workspace.sqlite3"))
        ticker = asyncio.create_task(scheduler(app.state.companion))
        mcp_stack = AsyncExitStack()
        clients = []
        try:
            await store.open()
            await store.recover_interrupted()
            selected = provider
            registry = echo_registry()
            daily_specs, daily_policy = companion_tools(app.state.companion)
            for spec in daily_specs:
                registry.register(spec)
            task_specs, task_policy = productivity_tools(app.state.companion)
            for spec in task_specs:
                registry.register(spec)
            workspace_specs = workspace_tools(app.state.workspace)
            for spec in workspace_specs:
                registry.register(spec)
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
                    embedding_client = httpx.AsyncClient()
                    clients.append(embedding_client)
                    selected = OpenAICompatibleProvider(config, chat_client)
                    try:
                        retriever = load_retriever(
                            embedding_client, settings.knowledge_path, settings.index_path
                        )
                    except RagError as error:
                        unavailable = error
                    else:
                        registry.register(search_knowledge_spec(retriever))
                        app.state.rag_available = True
                        app.state.embedding_provider = (
                            "local"
                            if type(retriever.embeddings).__name__ == "LocalEmbeddings"
                            else "remote"
                        )
                        app.state.embedding_model = retriever.embeddings.model
            if not app.state.rag_available:
                registry.register(search_knowledge_spec(unavailable=unavailable))
            if selected is not None and os.environ.get("HERTA_MCP_CONFIG"):
                from herta_agent.tools.mcp import connect_mcp_tools, load_mcp_config

                try:
                    config = load_mcp_config(os.environ["HERTA_MCP_CONFIG"])
                    specs = await mcp_stack.enter_async_context(
                        connect_mcp_tools(
                            config,
                            reserved_names=registry.names(),
                        )
                    )
                    for spec in specs:
                        registry.register(spec)
                    app.state.mcp_available = bool(specs)
                except Exception:
                    app.state.mcp_error = "mcp_unavailable"
            if selected is not None:
                agent = Agent(
                    selected,
                    settings.run,
                    registry=registry,
                    context_builder=CompanionContext(
                        PersonaContextBuilder(settings.soul_path), app.state.companion
                    ),
                    streaming=callable(getattr(selected, "stream", None)),
                    tool_policy=lambda spec: (
                        daily_policy(spec)
                        or task_policy(spec)
                        or any(
                            spec is trusted and trusted.name == "propose_file_plan"
                            for trusted in workspace_specs
                        )
                    ),
                )
                app.state.manager = RunManager(store, agent, settings)
            yield
        finally:
            await stop_scheduler(ticker)
            # A shutdown timeout must not close clients underneath a still-owned Run.
            if app.state.manager is not None:
                await app.state.manager.shutdown()
            else:
                await store.close()
            await app.state.workspace.shutdown()
            app.state.workspace.close()
            await mcp_stack.aclose()
            for client in reversed(clients):
                await client.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    app.include_router(companion_router())
    app.include_router(speech_router())
    app.include_router(workspace_router(settings))
    app.include_router(productivity_router(settings))

    @app.exception_handler(WorkspaceError)
    async def workspace_error(request, error):
        return error_response(422, "workspace_unavailable", str(error))

    @app.exception_handler(ValueError)
    async def companion_error(request, error):
        return error_response(422, "invalid_request", "日常操作参数无效，请检查时间或记录。")

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
            "active_runs": manager.active_count if manager else 0,
            "workspace_active_jobs": app.state.workspace.active_count,
            "embedding_provider": app.state.embedding_provider,
            "embedding_model": app.state.embedding_model,
            "mcp_available": app.state.mcp_available,
            "mcp_error": app.state.mcp_error,
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
        session, history, run = await app.state.store.get_session_snapshot(session_id)
        return {
            "session": session,
            "messages": [r for r in history if r.seq > after_seq][:limit],
            "current_run": run,
        }

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str):
        if app.state.manager is not None:
            return await app.state.manager.get(run_id)
        return {"run": await app.state.store.get_run(run_id), "cancel_requested": False}

    @app.get("/runs/{run_id}/diagnostics")
    async def get_diagnostics(run_id: str):
        return await app.state.store.get_diagnostics(run_id)

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

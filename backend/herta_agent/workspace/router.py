import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from herta_agent.tools.registry import ToolParameters

from .file_plans import FileOperation


class Grant(ToolParameters):
    path: str = Field(min_length=1, max_length=240)


class Sharing(ToolParameters):
    enabled: bool


class Analysis(ToolParameters):
    duplicates: bool = False


class PlanBody(ToolParameters):
    operations: list[FileOperation] = Field(min_length=1, max_length=100)


class Confirmation(ToolParameters):
    digest: str = Field(min_length=64, max_length=64)
    request_id: str = Field(min_length=1, max_length=64)


class DocumentsBody(ToolParameters):
    paths: list[str] = Field(min_length=1, max_length=20)
    semantic: bool = True


class TransformBody(ToolParameters):
    paths: list[str] = Field(min_length=1, max_length=10)
    kind: Literal["merge", "split", "rotate", "images", "docx_pdf"]
    target: str = Field(min_length=1, max_length=240)
    pages: list[int] = Field(default_factory=list, max_length=200)
    rotation: int = 0


class NoteBody(ToolParameters):
    target: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=100000)


def control_authorization(settings):
    async def authorize(request: Request):
        token = settings.workspace_token
        if not token:
            raise HTTPException(503, "文件工作台需要由桌面应用启动。")
        value = request.headers.get("authorization", "")
        if not secrets.compare_digest(value, f"Bearer {token}"):
            raise HTTPException(401, "目录授权需要桌面应用令牌。")

    return authorize


def workspace_router(settings):
    router = APIRouter(prefix="/workspace", dependencies=[Depends(control_authorization(settings))])

    @router.get("/roots")
    async def roots(request: Request):
        return request.app.state.workspace.roots()

    @router.post("/roots", status_code=201)
    async def grant(body: Grant, request: Request):
        return request.app.state.workspace.grant(body.path)

    @router.post("/roots/{root_id}/sharing")
    async def share(root_id: str, body: Sharing, request: Request):
        return request.app.state.workspace.share(root_id, body.enabled)

    @router.delete("/roots/{root_id}")
    async def revoke(root_id: str, request: Request):
        request.app.state.workspace.revoke(root_id)
        return {"ok": True}

    @router.get("/roots/{root_id}/files")
    async def listing(root_id: str, request: Request, path: str = ""):
        service = request.app.state.workspace
        return await service.io(service.list_files, root_id, path)

    @router.get("/roots/{root_id}/search")
    async def search(root_id: str, request: Request, query: str):
        service = request.app.state.workspace
        return await service.io(service.search, root_id, query)

    @router.get("/roots/{root_id}/text")
    async def text(root_id: str, request: Request, path: str, shared: bool = False):
        service = request.app.state.workspace
        return await service.io(service.read_text, root_id, path, shared=shared)

    @router.get("/roots/{root_id}/jobs")
    async def jobs(root_id: str, request: Request):
        return request.app.state.workspace.jobs(root_id)

    @router.post("/roots/{root_id}/jobs", status_code=201)
    async def start(root_id: str, body: Analysis, request: Request):
        return request.app.state.workspace.start_analysis(root_id, body.duplicates)

    @router.post("/jobs/{job_id}/cancel")
    async def cancel(job_id: str, request: Request):
        request.app.state.workspace.cancel(job_id)
        return {"ok": True}

    @router.post("/roots/{root_id}/plans", status_code=201)
    async def propose(root_id: str, body: PlanBody, request: Request):
        service = request.app.state.workspace
        return await service.io(service.plans.propose, root_id, body.operations)

    @router.get("/roots/{root_id}/plans")
    async def plans(root_id: str, request: Request):
        return request.app.state.workspace.plans.history(root_id)

    @router.get("/plans/{plan_id}")
    async def plan(plan_id: str, request: Request):
        return request.app.state.workspace.plans.get(plan_id, private=True)

    @router.get("/plans/{plan_id}/state")
    async def plan_state(plan_id: str, request: Request):
        service = request.app.state.workspace
        plan = service.plans.get(plan_id)
        service.root(plan["root_id"], shared=True)
        return {"plan": plan, "job": service.files.by_plan(plan_id)}

    @router.post("/plans/{plan_id}/confirm", status_code=201)
    async def confirm(plan_id: str, body: Confirmation, request: Request):
        return request.app.state.workspace.files.confirm(plan_id, body.digest, body.request_id)

    @router.get("/roots/{root_id}/file-jobs")
    async def file_jobs(root_id: str, request: Request):
        return request.app.state.workspace.files.history(root_id)

    @router.post("/file-jobs/{job_id}/cancel")
    async def stop_file(job_id: str, request: Request):
        request.app.state.workspace.files.cancel(job_id)
        return {"ok": True}

    @router.post("/file-jobs/{job_id}/undo")
    async def undo(job_id: str, request: Request):
        service = request.app.state.workspace
        job = service.files.get(job_id)

        def preview(root_id, cancel=None):
            service.check_cancel(cancel)
            return service.plans.preview_undo(job_id)

        return await service.io(preview, job["root_id"])

    @router.get("/roots/{root_id}/document")
    async def document(root_id: str, request: Request, path: str):
        service = request.app.state.workspace
        return await service.io(service.documents.read, root_id, path)

    @router.post("/roots/{root_id}/document-index")
    async def index(root_id: str, body: DocumentsBody, request: Request):
        service = request.app.state.workspace
        return await service.io(
            service.documents.index, root_id, body.paths, semantic=body.semantic
        )

    @router.get("/roots/{root_id}/knowledge")
    async def knowledge(root_id: str, request: Request, query: str, semantic: bool = True):
        service = request.app.state.workspace
        return await service.io(service.documents.search, root_id, query, semantic=semantic)

    @router.get("/roots/{root_id}/document-index")
    async def catalog(root_id: str, request: Request):
        return request.app.state.workspace.documents.catalog(root_id)

    @router.delete("/roots/{root_id}/document-index")
    async def forget(root_id: str, request: Request, path: str):
        return request.app.state.workspace.documents.forget(root_id, path)

    @router.post("/roots/{root_id}/transform", status_code=201)
    async def transform(root_id: str, body: TransformBody, request: Request):
        service = request.app.state.workspace
        return await service.io(
            service.documents.transform,
            root_id,
            body.paths,
            body.kind,
            body.target,
            pages=body.pages,
            rotation=body.rotation,
        )

    @router.post("/roots/{root_id}/vault")
    async def vault(root_id: str, request: Request):
        return request.app.state.workspace.documents.bind_vault(root_id)

    @router.get("/document-settings")
    async def document_settings(request: Request):
        return request.app.state.workspace.documents.settings()

    @router.post("/roots/{root_id}/note", status_code=201)
    async def note(root_id: str, body: NoteBody, request: Request):
        service = request.app.state.workspace
        return await service.io(service.documents.note, root_id, body.target, body.text)

    return router

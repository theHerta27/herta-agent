import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from herta_agent.tools.registry import ToolParameters


class Grant(ToolParameters):
    path: str = Field(min_length=1, max_length=240)


class Sharing(ToolParameters):
    enabled: bool


class Analysis(ToolParameters):
    duplicates: bool = False


def workspace_router(settings):
    async def authorize(request: Request):
        token = settings.workspace_token
        if not token:
            raise HTTPException(503, "文件工作台需要由桌面应用启动。")
        value = request.headers.get("authorization", "")
        if not secrets.compare_digest(value, f"Bearer {token}"):
            raise HTTPException(401, "目录授权需要桌面应用令牌。")

    router = APIRouter(prefix="/workspace", dependencies=[Depends(authorize)])

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
    async def text(root_id: str, request: Request, path: str):
        service = request.app.state.workspace
        return await service.io(service.read_text, root_id, path)

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

    return router

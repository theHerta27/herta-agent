from fastapi import APIRouter, Depends, Request

from herta_agent.workspace.router import control_authorization

from .models import (
    GoalChange,
    GoalInput,
    MaterialChange,
    MaterialInput,
    RecitationInput,
    Revision,
    RoleInput,
    TaskChange,
    TaskInput,
)


def productivity_router(settings):
    router = APIRouter(
        prefix="/productivity", dependencies=[Depends(control_authorization(settings))]
    )

    def store(request):
        return request.app.state.companion.productivity

    @router.get("")
    async def snapshot(request: Request):
        value = store(request).snapshot()
        value["reviews"] = store(request).review_suggestions()
        return value

    @router.post("/tasks", status_code=201)
    async def task(body: TaskInput, request: Request):
        return store(request).create_task(body.model_dump())

    @router.post("/tasks/{identifier}")
    async def change_task(identifier: str, body: TaskChange, request: Request):
        return store(request).update_task(
            identifier,
            body.action,
            body.revision,
            **body.model_dump(exclude={"action", "revision"}, exclude_unset=True),
        )

    @router.get("/tasks/{identifier}/history")
    async def history(identifier: str, request: Request):
        return store(request).history(identifier)

    @router.post("/goals", status_code=201)
    async def goal(body: GoalInput, request: Request):
        return store(request).create_goal(body.model_dump())

    @router.post("/goals/{identifier}")
    async def change_goal(identifier: str, body: GoalChange, request: Request):
        return store(request).update_goal(identifier, body.status, body.revision)

    @router.post("/materials", status_code=201)
    async def material(body: MaterialInput, request: Request):
        if body.root_id:
            request.app.state.workspace.resolve(body.root_id, body.path, text=True)
        return store(request).add_material(body.model_dump())

    @router.post("/materials/{identifier}")
    async def change_material(identifier: str, body: MaterialChange, request: Request):
        return store(request).update_material(
            identifier, body.revision, progress=body.progress, notes=body.notes
        )

    @router.post("/materials/{identifier}/review")
    async def review(identifier: str, body: Revision, request: Request):
        return store(request).review(identifier, body.revision)

    @router.get("/materials/{identifier}/document")
    async def document(identifier: str, request: Request):
        p = store(request)
        material = next((m for m in p.snapshot()["materials"] if m["id"] == identifier), None)
        if not material or not material["root_id"]:
            raise ValueError("此学习记录未关联本机资料。")
        w = request.app.state.workspace
        return await w.io(w.documents.read, material["root_id"], material["path"])

    @router.post("/role")
    async def role(body: RoleInput, request: Request):
        return store(request).set_role(body.role)

    @router.post("/recitation")
    async def recitation(body: RecitationInput, request: Request):
        return store(request).compare_recitation(body.expected, body.transcript)

    return router

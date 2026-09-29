from pydantic import BaseModel, ConfigDict, Field

from herta_agent.tools.registry import ToolParameters, ToolSpec


class PlanStep(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=500)


class PlanParameters(ToolParameters):
    steps: list[PlanStep] = Field(min_length=1, max_length=12)


def propose_plan():
    async def propose(p):
        return {"steps": [step.model_dump() for step in p.steps]}

    return ToolSpec(
        "propose_plan",
        "提出分步计划，不执行操作，也不表示步骤已完成。修改前先规划。",
        PlanParameters,
        propose,
    )

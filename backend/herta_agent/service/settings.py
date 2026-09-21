import os

from pydantic import BaseModel, ConfigDict, Field

from herta_agent.runtime.errors import AgentError


class ServiceSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    max_active_runs: int = Field(default=4, strict=True, ge=1, le=32)

    @classmethod
    def from_env(cls) -> "ServiceSettings":
        try:
            return cls(max_active_runs=int(os.environ.get("HERTA_MAX_ACTIVE_RUNS", "4")))
        except ValueError:
            raise AgentError("HERTA_MAX_ACTIVE_RUNS必须为1–32的整数。") from None

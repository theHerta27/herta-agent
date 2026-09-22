import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from herta_agent.config import RunSettings
from herta_agent.runtime.errors import AgentError

ROOT = Path(__file__).resolve().parents[3]


class ServiceSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    max_active_runs: int = Field(default=4, strict=True, ge=1, le=32)
    db_path: Path = ROOT / ".local" / "sessions.sqlite3"
    soul_path: Path = ROOT / "persona" / "soul.md"
    knowledge_path: Path = ROOT / "knowledge"
    index_path: Path = ROOT / ".local" / "rag"
    provider: Literal["openai", "demo"] = "openai"
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8765, strict=True, ge=0, le=65535)
    workers: Literal[1] = 1
    event_wait_seconds: float = Field(default=2.0, strict=True, ge=0.01, le=30)
    send_wait_seconds: float = Field(default=5.0, strict=True, ge=0.01, le=60)
    heartbeat_seconds: float = Field(default=10.0, strict=True, ge=0.01, le=60)
    run: RunSettings = Field(default_factory=RunSettings)

    @field_validator("db_path", "soul_path", "knowledge_path", "index_path")
    @classmethod
    def absolute_path(cls, path):
        return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()

    @classmethod
    def from_env(cls) -> "ServiceSettings":
        try:
            fields = {
                "max_active_runs": int(os.environ.get("HERTA_MAX_ACTIVE_RUNS", "4")),
                "port": int(os.environ.get("HERTA_SERVICE_PORT", "8765")),
                "workers": int(os.environ.get("WEB_CONCURRENCY", "1")),
                "provider": os.environ.get("HERTA_SERVICE_PROVIDER", "openai"),
            }
            for field, env in (
                ("db_path", "HERTA_SERVICE_DB"),
                ("soul_path", "HERTA_SOUL_PATH"),
                ("knowledge_path", "HERTA_KNOWLEDGE"),
                ("index_path", "HERTA_RAG_INDEX"),
            ):
                if env in os.environ:
                    fields[field] = os.environ[env]
            return cls(**fields)
        except ValueError:
            raise AgentError(
                "服务配置无效；要求单worker、有效路径/端口和1–32的并发上限。"
            ) from None

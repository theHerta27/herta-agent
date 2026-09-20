"""A tool's schema and its handler are registered together."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


class ToolParameters(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: type[ToolParameters]
    handler: Callable[[ToolParameters], Awaitable[object]]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", self.name):
            raise ValueError("Invalid tool name")
        if not self.description.strip() or not issubclass(self.parameters, ToolParameters):
            raise ValueError("A tool requires a description and ToolParameters model")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def definitions(self) -> tuple[dict, ...]:
        return tuple(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters.model_json_schema(),
                },
            }
            for spec in self._tools.values()
        )

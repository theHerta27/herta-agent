"""The only Phase 2 tool: echo text, optionally waiting to demonstrate cancellation."""

import asyncio

from pydantic import Field

from herta_agent.tools.registry import ToolParameters, ToolRegistry, ToolSpec


class EchoParameters(ToolParameters):
    text: str = Field(min_length=1, max_length=10000)
    delay_seconds: float = Field(default=0.0, ge=0, le=30)


async def echo(parameters: EchoParameters) -> dict[str, str]:
    await asyncio.sleep(parameters.delay_seconds)
    return {"text": parameters.text}


def echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "echo", "Return the given text; optional delay in seconds (0–30).", EchoParameters, echo
        )
    )
    return registry

"""Two fixed demo tools: no user files, credentials, model, index or network."""

from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP("Herta fixed demo")
readonly = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True
)


@server.tool(annotations=readonly)
def herta_demo_status() -> dict[str, str]:
    """Return the fixed demo server status, not live Herta application state."""
    return {"source": "fixed_demo", "status": "ready"}


@server.tool(annotations=readonly)
def herta_demo_fact(topic: Literal["harness", "knowledge"]) -> dict[str, str]:
    """Return a fixed demo fact about the Herta harness or knowledge tool."""
    facts = {
        "harness": "Herta uses one agent loop and a shared ToolRegistry/ToolExecutor boundary.",
        "knowledge": "search_knowledge returns evidence from the configured Herta knowledge index.",
    }
    return {"source": "fixed_demo", "topic": topic, "text": facts[topic]}


if __name__ == "__main__":
    server.run(transport="stdio")

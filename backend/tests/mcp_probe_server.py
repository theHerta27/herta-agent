"""Real SDK server for adapter boundary tests; no network or user data."""

import asyncio
import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP("Adapter probe")
readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


@server.tool(annotations=readonly)
def probe_read() -> dict:
    return {"value": "fixture"}


@server.tool(annotations=readonly)
def probe_fail() -> str:
    raise RuntimeError("private-key")


@server.tool(annotations=readonly)
async def probe_slow() -> str:
    await asyncio.sleep(2)
    return "late"


@server.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
)
def probe_write() -> str:
    return "not allowed"


@server.tool()
def probe_unspecified() -> str:
    return "not allowed"


@server.tool(annotations=readonly)
def probe_disconnect() -> str:
    """Simulate a lost server process during a call."""
    os._exit(0)


@server.tool(annotations=readonly)
async def probe_invalid_bytes() -> str:
    """Break UTF-8 transport after SDK initialization and tool discovery."""
    os.write(1, b"\xff\n")
    await asyncio.Event().wait()
    return "unreachable"


if __name__ == "__main__":
    server.run(transport="stdio")

# Minimal read-only MCP demo

This opt-in adapter launches one explicitly configured local process through the
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0).
Its tools share Herta's ToolRegistry and ToolExecutor: argument validation,
permission checks, timeout, cancellation and JSON result envelopes all use the
existing execution boundary.

`sample_server.py` exposes `herta_demo_status` and `herta_demo_fact`. Both return
fixed demo data marked `source: fixed_demo`; neither reads user files, calls a
model, searches the real knowledge index, or uses the network. The status is the
sample server's fixed status, not a health check of the Herta application.

## Configuration

Install the backend dependencies (`uv sync --project backend --extra dev`). Copy
`config.example.json` to a local JSON file and replace both absolute paths with
your actual Python executable and sample script. Keep commands and arguments in
this public configuration free of credentials. Set `HERTA_MCP_CONFIG` to the JSON
file's absolute path before starting the backend. Leaving it unset keeps MCP off.
Invalid configuration, unavailable processes and unsafe tool discovery disable
only this optional integration; ordinary chat and local tools remain usable.

The config permits exactly one server. `command` must be an existing absolute
executable path; `args` is passed as an argument list through the SDK, with no
shell interpolation. `allowed_tools` must be a nonempty list of unique tool
names. `timeout` is the per-tool deadline in seconds, between 0 and 600. Startup
initialization/discovery has a separate 10-second deadline; SDK shutdown can add
its bounded process termination grace period.

An allowlist entry is authorization to expose that tool; the server must also
advertise `readOnlyHint: true` and must not advertise `destructiveHint: true`.
The sample explicitly sets `destructiveHint: false`. A non-destructive or
idempotent hint alone never grants execution. Missing entries, duplicate or
invalid advertised names, collisions with local tools, and invalid schemas reject
the whole optional catalog atomically.

The adapter supports JSON Schema object arguments using Draft 2020-12 validation,
including local references, constraints and enums. External schema references
are rejected. Simple schemas default unspecified top-level `additionalProperties`
to false, following Herta's strict argument boundary; explicitly advertised
policies and composed/reference schemas retain their schema semantics. Results
support structured JSON or text content. Images, audio and embedded resources
are rejected. The shared executor rejects results over 64,000 UTF-8 bytes rather
than treating truncated data as success.

Child processes inherit the SDK's small list of ordinary process environment
variables, not Herta API keys; the config does not accept an `env` map. Child
stderr and raw SDK protocol diagnostics are suppressed to avoid credential or
untrusted-content leakage. Visible errors use fixed safe messages. The app can
report optional integration failure without displaying process commands, paths,
remote exception bodies, or raw schemas.

MCP declarations are trust signals, not an OS sandbox. Only configure a local
server whose executable and implementation you trust. V1 does not support
side-effect grants, remote servers, OAuth, automatic discovery, retries or tool
markets.

## Runtime integration

```python
from contextlib import AsyncExitStack
from herta_agent.tools.mcp import MCPAdapterError, connect_mcp_tools, load_mcp_config

async with AsyncExitStack() as stack:
    try:
        config = load_mcp_config(config_path)
        reserved = [
            definition["function"]["name"] for definition in registry.definitions()
        ]
        specs = await stack.enter_async_context(
            connect_mcp_tools(config, reserved_names=reserved)
        )
    except MCPAdapterError:
        specs = ()  # Optional MCP failure leaves the existing local registry available.
    for spec in specs:
        registry.register(spec)
    # Keep the context open for the entire service lifespan.
```

The adapter owns SDK contexts in a dedicated task and enters/exits them there. Transport faults, including invalid UTF-8 after initialization, close the tool connection without cancelling the application lifespan. Pending calls are cancelled and drained; subsequent calls return `mcp_unavailable`. After context closure,
previously yielded handlers return `mcp_unavailable`. Execute calls through
ToolExecutor rather than calling handlers directly.

## Verification

From the repository root, using your installed project environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_mcp.py -v
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_tool_permissions.py -v
```

The integration tests launch actual SDK stdio subprocesses and require no
network, external model, or API credentials.
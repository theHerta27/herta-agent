import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import types
from pydantic import ValidationError

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.mcp import (
    MCPAdapterError,
    MCPConfig,
    _parameters,
    connect_mcp_tools,
    load_mcp_config,
)
from herta_agent.tools.registry import ToolRegistry, ToolSpec

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "mcp" / "sample_server.py"
FIXTURE = Path(__file__).with_name("mcp_probe_server.py")


def config(*names, script=SAMPLE, timeout=2):
    return MCPConfig.model_validate(
        {
            "servers": [
                {
                    "name": "demo",
                    "command": sys.executable,
                    "args": [str(script)],
                    "allowed_tools": list(names),
                    "timeout": timeout,
                }
            ]
        }
    )


class MCPConfigTests(unittest.TestCase):
    def test_public_config_accepts_only_one_explicit_executable_and_allowlist(self):
        valid = config("herta_demo_status").model_dump(mode="json")
        cases = [
            {"servers": []},
            {"servers": valid["servers"] * 2},
            {"servers": [{**valid["servers"][0], "command": "python"}]},
            {"servers": [{**valid["servers"][0], "allowed_tools": []}]},
            {"servers": [{**valid["servers"][0], "allowed_tools": ["bad.tool"]}]},
            {"servers": [{**valid["servers"][0], "allowed_tools": ["same", "same"]}]},
            {"servers": [{**valid["servers"][0], "env": {"KEY": "secret"}}]},
            {"servers": [{**valid["servers"][0], "timeout": 0}]},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                MCPConfig.model_validate(case)

    def test_invalid_config_error_does_not_echo_path_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"secret":"private-key"}', encoding="utf-8")
            with self.assertRaises(MCPAdapterError) as raised:
                load_mcp_config(path)
        self.assertNotIn("private-key", str(raised.exception))
        self.assertNotIn(str(path), str(raised.exception))


class MCPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_discovery_schema_executor_and_closed_lifecycle(self):
        async with connect_mcp_tools(config("herta_demo_status", "herta_demo_fact")) as specs:
            registry = ToolRegistry()
            for spec in specs:
                registry.register(spec)
            self.assertEqual(
                {spec.name for spec in specs}, {"herta_demo_status", "herta_demo_fact"}
            )
            result = await ToolExecutor(registry).execute(
                ToolCall(id="a", name="herta_demo_status", arguments="{}")
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.data, {"source": "fixed_demo", "status": "ready"})
            result = await ToolExecutor(registry).execute(
                ToolCall(id="b", name="herta_demo_fact", arguments='{"topic":"harness"}')
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.data["source"], "fixed_demo")
            started = []

            async def on_started():
                started.append(True)

            for args in ('{"topic":3}', '{"topic":"missing"}', '{"topic":"harness","extra":1}'):
                result = await ToolExecutor(registry).execute(
                    ToolCall(id="bad", name="herta_demo_fact", arguments=args),
                    on_started=on_started,
                )
                self.assertEqual(result.error.code, "invalid_arguments")
            self.assertEqual(started, [])
        result = await ToolExecutor(registry).execute(
            ToolCall(id="closed", name="herta_demo_status", arguments="{}")
        )
        self.assertEqual(result.error.code, "mcp_unavailable")

    async def test_allowlist_and_read_only_hint_are_both_required(self):
        async with connect_mcp_tools(config("probe_read", script=FIXTURE)) as specs:
            self.assertEqual([spec.name for spec in specs], ["probe_read"])
        for name in ("probe_write", "probe_unspecified", "missing"):
            with self.subTest(name=name), self.assertRaises(MCPAdapterError):
                async with connect_mcp_tools(config(name, script=FIXTURE)):
                    self.fail("unsafe or absent tool was registered")

    async def test_collisions_invalid_schema_and_external_refs_are_rejected(self):
        with self.assertRaises(MCPAdapterError):
            async with connect_mcp_tools(
                config("herta_demo_status"), reserved_names={"herta_demo_status"}
            ):
                self.fail("collision accepted")
        schema_cases = (
            {"type": "object", "properties": {"x": {"type": "invalid"}}},
            {"type": "object", "$ref": "https://example.com/schema.json"},
            {"type": "array"},
        )
        for schema in schema_cases:
            advertised = types.ListToolsResult(
                tools=[
                    types.Tool(
                        name="herta_demo_status",
                        description="status",
                        inputSchema=schema,
                        annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False),
                    )
                ]
            )
            with (
                self.subTest(schema=schema),
                patch("herta_agent.tools.mcp.ClientSession.list_tools", return_value=advertised),
                self.assertRaises(MCPAdapterError),
            ):
                async with connect_mcp_tools(config("herta_demo_status")):
                    self.fail("invalid schema accepted")

    async def test_remote_errors_timeout_cancel_and_next_call_are_safe(self):
        async with connect_mcp_tools(
            config("probe_read", "probe_fail", "probe_slow", script=FIXTURE, timeout=0.1)
        ) as specs:
            registry = ToolRegistry()
            for spec in specs:
                registry.register(spec)
            executor = ToolExecutor(registry)
            failed = await executor.execute(ToolCall(id="err", name="probe_fail", arguments="{}"))
            self.assertEqual(failed.error.code, "mcp_tool_error")
            self.assertNotIn("private-key", failed.to_json())
            slow = await executor.execute(ToolCall(id="slow", name="probe_slow", arguments="{}"))
            self.assertEqual(slow.error.code, "timeout")
            task = asyncio.create_task(
                executor.execute(ToolCall(id="cancel", name="probe_slow", arguments="{}"))
            )
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(
                (await executor.execute(ToolCall(id="after", name="probe_read", arguments="{}"))).ok
            )

    async def test_startup_failure_is_safe_and_no_tools_are_yielded(self):
        unavailable = config("status")
        unavailable.servers[0].args = [str(SAMPLE.with_name("private-key-missing.py"))]
        with self.assertRaises(MCPAdapterError) as raised:
            async with connect_mcp_tools(unavailable):
                self.fail("unavailable server connected")
        self.assertNotIn("private-key", str(raised.exception))

    async def test_malformed_server_output_and_startup_timeout_do_not_leak_logs(self):
        broken = config("status")
        broken.servers[0].args = [
            "-c",
            "import time; print('{invalid private-key}', flush=True); time.sleep(30)",
        ]
        with (
            patch("herta_agent.tools.mcp._STARTUP_SECONDS", 0.2),
            self.assertNoLogs(level="WARNING"),
            self.assertRaises(MCPAdapterError),
        ):
            async with connect_mcp_tools(broken):
                self.fail("invalid protocol server connected")

    async def test_invalid_and_duplicate_advertised_names_are_rejected(self):
        safe = types.Tool(
            name="herta_demo_status",
            description="Status",
            inputSchema={"type": "object"},
            annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )
        for tools in ([safe, safe], [safe, safe.model_copy(update={"name": "bad.tool"})]):
            with (
                self.subTest(names=[tool.name for tool in tools]),
                patch(
                    "herta_agent.tools.mcp.ClientSession.list_tools",
                    return_value=types.ListToolsResult(tools=tools),
                ),
                self.assertRaises(MCPAdapterError),
            ):
                async with connect_mcp_tools(config("herta_demo_status")):
                    self.fail("unsafe tool catalog accepted")

    async def test_local_refs_and_constraints_are_preserved_in_registry_and_executor(self):
        schema = {
            "type": "object",
            "properties": {"count": {"$ref": "#/$defs/count"}},
            "$defs": {"count": {"type": "integer", "minimum": 1, "maximum": 3}},
            "required": ["count"],
            "additionalProperties": False,
        }
        advertised = types.ListToolsResult(
            tools=[
                types.Tool(
                    name="probe_read",
                    description="Read",
                    inputSchema=schema,
                    annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False),
                )
            ]
        )
        with patch("herta_agent.tools.mcp.ClientSession.list_tools", return_value=advertised):
            async with connect_mcp_tools(config("probe_read", script=FIXTURE)) as specs:
                registry = ToolRegistry()
                registry.register(specs[0])
                self.assertEqual(registry.definitions()[0]["function"]["parameters"], schema)
                for arguments in (
                    "{}",
                    '{"count":true}',
                    '{"count":0}',
                    '{"count":4}',
                    '{"count":NaN}',
                    '{"count":"2"}',
                ):
                    with self.subTest(arguments=arguments):
                        result = await ToolExecutor(registry).execute(
                            ToolCall(id="bad", name="probe_read", arguments=arguments)
                        )
                        self.assertEqual(result.error.code, "invalid_arguments")
                self.assertEqual(
                    specs[0].parameters.model_validate_json('{"count":2}').model_dump(),
                    {"count": 2},
                )

    async def test_disconnected_server_returns_safe_failure(self):
        async with connect_mcp_tools(config("probe_disconnect", script=FIXTURE)) as specs:
            registry = ToolRegistry()
            registry.register(specs[0])
            result = await ToolExecutor(registry).execute(
                ToolCall(id="a", name="probe_disconnect", arguments="{}")
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "mcp_unavailable")

    async def test_root_ref_schema_accepts_fields_defined_in_local_definition(self):
        schema = {
            "type": "object",
            "$ref": "#/$defs/Arguments",
            "$defs": {
                "Arguments": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "minimum": 1}},
                    "required": ["count"],
                    "additionalProperties": False,
                }
            },
        }

        async def handle(arguments):
            return arguments.model_dump()

        registry = ToolRegistry()
        registry.register(ToolSpec("local_ref", "Read", _parameters(schema), handle))
        result = await ToolExecutor(registry).execute(
            ToolCall(id="a", name="local_ref", arguments='{"count":2}')
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"count": 2})

    async def test_invalid_utf8_after_discovery_does_not_cancel_connection_owner(self):
        owner = asyncio.current_task()
        async with connect_mcp_tools(
            config("probe_invalid_bytes", script=FIXTURE, timeout=5)
        ) as specs:
            registry = ToolRegistry()
            registry.register(specs[0])
            caller = asyncio.create_task(
                ToolExecutor(registry).execute(
                    ToolCall(id="fault", name="probe_invalid_bytes", arguments="{}")
                )
            )
            result = await caller
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "mcp_unavailable")
            self.assertEqual(owner.cancelling(), 0)
            # Normal local tools remain callable after the optional transport crashes.
            from herta_agent.tools.echo import echo_registry

            local = await ToolExecutor(echo_registry()).execute(
                ToolCall(id="local", name="echo", arguments='{"text":"still usable"}')
            )
            self.assertTrue(local.ok)
        self.assertFalse(
            any(task.get_name() == "herta-mcp-connection" for task in asyncio.all_tasks())
        )

    async def test_cancel_during_startup_drains_owned_connection(self):
        config_data = config("status")
        config_data.servers[0].args = ["-c", "import time; time.sleep(30)"]

        async def startup():
            async with connect_mcp_tools(config_data):
                self.fail("hanging server initialized")

        caller = asyncio.create_task(startup())
        await asyncio.sleep(0.05)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertFalse(
            any(task.get_name().startswith("herta-mcp-") for task in asyncio.all_tasks())
        )

    async def test_cancel_lifespan_drains_connection_without_swallowing_cancellation(self):
        connected = asyncio.Event()

        async def lifespan():
            async with connect_mcp_tools(config("herta_demo_status")):
                connected.set()
                await asyncio.Event().wait()

        caller = asyncio.create_task(lifespan())
        await asyncio.wait_for(connected.wait(), 5)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertFalse(
            any(task.get_name().startswith("herta-mcp-") for task in asyncio.all_tasks())
        )

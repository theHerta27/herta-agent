import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

from herta_agent.rag.__main__ import command, parser


class RagCLITests(unittest.IsolatedAsyncioTestCase):
    async def test_build_inspect_with_real_adapter_mock_transport(self):
        requests = []
        secret = uuid.uuid4().hex

        def handler(request):
            requests.append(request)
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": i, "embedding": [1.0, i + 1.0]}
                        for i, _ in enumerate(payload["input"])
                    ]
                },
            )

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(
                os.environ,
                {
                    "HERTA_EMBEDDING_BASE_URL": "https://embedding.invalid/v1",
                    "HERTA_EMBEDDING_MODEL": "fixture",
                    "HERTA_EMBEDDING_API_KEY": secret,
                },
                clear=True,
            ),
        ):
            output = io.StringIO()
            root = Path(temporary) / "中文 索引"
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with contextlib.redirect_stdout(output):
                    await command(parser().parse_args(["--index", str(root), "build"]), client)
                    await command(
                        parser().parse_args(["--index", str(root), "inspect", "人物关系"]), client
                    )
            self.assertEqual(len(requests), 2)
            self.assertIn("candidates", output.getvalue())
            self.assertNotIn(secret, output.getvalue())
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())

    async def test_missing_configuration_cli_sanitized(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("HERTA_")}
        env["HERTA_EMBEDDING_PROVIDER"] = "remote"
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "herta_agent.rag", "build"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("embedding_config", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

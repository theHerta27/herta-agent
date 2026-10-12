import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


class HertaSpeechTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.worker = self.root / "worker.py"
        self.worker.write_text(
            """import json,sys,wave,time
print(json.dumps({"type":"ready","protocol":1}),flush=True)
for line in sys.stdin:
 r=json.loads(line)
 if r.get("command")=="shutdown":
  print(json.dumps({"id":r["id"],"ok":True,"shutdown":True}),flush=True); break
 if r["text"]=="stall": time.sleep(120)
 with wave.open(r["output_path"],"wb") as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(32000);w.writeframes(b"\\x01\\x02"*320)
 print(json.dumps({"id":r["id"],"ok":True,"wav_path":r["output_path"]}),flush=True)
""",
            encoding="utf-8",
        )

    def service(self):
        from herta_agent.companion.herta_speech import HertaSpeech

        return HertaSpeech(self.root, python=Path(sys.executable), worker=self.worker)

    async def test_owned_ready_synthesis_shutdown_removes_outputs(self):
        service = self.service()
        wav = await service.synthesize("你好", "happy")
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertEqual(service.active_children, 0)
        self.assertFalse(list(self.root.glob("speech-*")))

    async def test_cancel_joins_only_owned_child_and_cleans_temp(self):
        service = self.service()
        work = asyncio.create_task(service.synthesize("stall", "neutral"))
        for _ in range(100):
            if service.active_children:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        work.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await work
        self.assertEqual(service.active_children, 0)
        self.assertFalse(list(self.root.glob("speech-*")))

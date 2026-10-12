import asyncio
import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


class HertaSpeechTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.worker = self.root / "worker.py"
        self.worker.write_text(
            """import json,sys,wave,time,os
from pathlib import Path
p=Path('starts'); p.write_text(str(int(p.read_text())+1 if p.exists() else 1))
Path('actual.pid').write_text(str(os.getpid()))
print(json.dumps({"type":"ready","protocol":1}),flush=True)
for line in sys.stdin:
 r=json.loads(line)
 if r.get("command")=="shutdown":
  print(json.dumps({"id":r["id"],"ok":True,"shutdown":True}),flush=True); break
 if r["text"]=="stall": time.sleep(120)
 if r["text"]=="waiting":
  Path('waiting').write_text('ready')
  while not Path('release').exists(): time.sleep(.01)
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
        await service.shutdown()

    async def test_repeated_speech_reuses_loaded_worker_and_shutdown_releases_it(self):
        service = self.service()
        try:
            await service.synthesize("第一句")
            await service.synthesize("第二句")
            self.assertEqual((self.root / "starts").read_text(), "1", "重复朗读不能重新加载模型")
            self.assertEqual(service.active_children, 0)
            self.assertEqual(service.resident_children, 1)
            self.assertFalse(list(self.root.glob("speech-*")))
        finally:
            await service.shutdown()
        self.assertEqual(service.resident_children, 0)

    async def test_prewarm_and_idle_expiry_keep_requests_separate_from_resident_model(self):
        from herta_agent.companion.herta_speech import HertaSpeech

        service = HertaSpeech(
            self.root, python=Path(sys.executable), worker=self.worker, idle_seconds=0.15
        )
        try:
            await service.warmup()
            self.assertEqual(service.active_children, 0)
            await service.synthesize("已预热")
            self.assertEqual((self.root / "starts").read_text(), "1")
            for _ in range(100):
                if not service.resident_children:
                    break
                await asyncio.sleep(0.02)
            self.assertEqual(service.resident_children, 0)
        finally:
            await service.shutdown()

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

    async def test_cancelling_queued_speech_does_not_kill_current_speech(self):
        service = self.service()
        first = asyncio.create_task(service.synthesize("waiting"))
        second = None
        try:
            for _ in range(100):
                if (self.root / "waiting").exists():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue((self.root / "waiting").exists())
            second = asyncio.create_task(service.synthesize("第二句"))
            await asyncio.sleep(0.03)
            second.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await second
            (self.root / "release").write_text("go")
            self.assertTrue((await first).startswith(b"RIFF"))
        finally:
            (self.root / "release").write_text("go")
            await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
            await service.shutdown()

    @unittest.skipUnless(os.name == "nt", "Windows process-tree ownership")
    async def test_cancel_isolated_venv_joins_its_actual_interpreter(self):
        from ctypes import wintypes

        from herta_agent.companion.herta_speech import HertaSpeech

        interpreter = PROJECT / ".local/gpt-sovits/.venv/Scripts/python.exe"
        if not interpreter.is_file():
            self.skipTest("optional local voice runtime")
        service = HertaSpeech(self.root, python=interpreter, worker=self.worker)
        task = asyncio.create_task(service.synthesize("stall"))
        handle = None
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        try:
            for _ in range(200):
                if (self.root / "actual.pid").exists():
                    break
                await asyncio.sleep(0.02)
            self.assertTrue((self.root / "actual.pid").exists())
            handle = kernel.OpenProcess(0x1001, False, int((self.root / "actual.pid").read_text()))
            self.assertTrue(handle)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), 5)
            kernel.WaitForSingleObject(handle, 1000)
            result = wintypes.DWORD()
            self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(result)))
            self.assertNotEqual(result.value, 259, "不能只停止venv启动器而留下真实解释器")
            self.assertEqual(service.resident_children, 0)
        finally:
            if handle:
                kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await service.shutdown()

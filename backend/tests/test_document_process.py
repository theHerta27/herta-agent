import os
import subprocess
import sys
import unittest

from herta_agent.documents.process import attach_job


@unittest.skipUnless(os.name == "nt", "Native Windows Job memory limit")
class DocumentProcessTests(unittest.TestCase):
    def test_document_process_cannot_exceed_its_owned_job_memory_limit(self):
        code = (
            "import sys; sys.stdin.buffer.read(1)\ntry:\n"
            " x=bytearray(256*1024*1024); print('unbounded')\n"
            "except MemoryError:\n print('bounded')"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=0x08000000,
        )
        job = None
        try:
            job = attach_job(child, memory_limit=128 * 1024 * 1024)
            output, _ = child.communicate(b"x", timeout=10)
            self.assertIn(b"bounded", output)
        finally:
            if job:
                job[0].CloseHandle(job[1])
            if child.poll() is None:
                child.kill()
            child.communicate()

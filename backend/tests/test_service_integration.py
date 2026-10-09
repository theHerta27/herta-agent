"""Actual loopback sockets and Windows-compatible process failure tests."""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

import httpx

PROBE = Path(__file__).with_name("service_probe.py")


class ServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="herta 服务 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "sessions.sqlite3"
        self.proc = None
        self.addCleanup(self.stop)
        self.start()

    def start(self):
        ready = self.root / "port.txt"
        ready.unlink(missing_ok=True)
        self.log = (self.root / "server.log").open("ab")
        self.proc = subprocess.Popen(
            [sys.executable, str(PROBE), str(self.root)],
            cwd=self.root,
            env={k: v for k, v in os.environ.items() if not k.startswith("HERTA_")},
            stdin=subprocess.PIPE,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.client = httpx.Client(trust_env=False, timeout=3)

        def ready_server():
            if self.proc.poll() is not None:
                self.fail((self.root / "server.log").read_text(errors="replace"))
            if ready.exists():
                self.port = int(ready.read_text())
                self.url = f"http://127.0.0.1:{self.port}"
                try:
                    return self.client.get(self.url + "/health").status_code == 200
                except httpx.TransportError:
                    pass
            return False

        self.wait(ready_server)

    def stop(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.stdin.write(b"x")
                self.proc.stdin.flush()
            self.proc.wait(timeout=5)
            self.proc.stdin.close()
            self.proc = None
        if hasattr(self, "client"):
            self.client.close()
        if hasattr(self, "log"):
            self.log.close()

    def wait(self, predicate, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            time.sleep(0.02)
        self.fail("Timed out waiting for local service condition")

    def session(self):
        response = self.client.post(self.url + "/sessions")
        response.raise_for_status()
        return response.json()["session_id"]

    def snapshot(self, sid):
        return self.client.get(self.url + f"/sessions/{sid}").json()

    def status(self, sid, status):
        def matches():
            snapshot = self.snapshot(sid)
            run = snapshot["current_run"]
            return snapshot if run and run["status"] == status else None

        return self.wait(matches)

    def raw(self, sid, text):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        sock.settimeout(4)
        sock.connect(("127.0.0.1", self.port))
        body = json.dumps({"text": text}).encode()
        sock.sendall(
            (
                f"POST /sessions/{sid}/runs HTTP/1.1\r\nHost: localhost\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode()
            + body
        )
        self.addCleanup(sock.close)
        return sock

    def events(self, response):
        for line in response.iter_lines():
            if line.startswith("data: "):
                yield json.loads(line[6:])

    def test_parallel_capacity_cancel_and_reuse(self):
        a, b, c = self.session(), self.session(), self.session()
        with self.client.stream(
            "POST", self.url + f"/sessions/{a}/runs", json={"text": "wait"}
        ) as first:
            events = self.events(first)
            started = next(events)
            self.assertEqual(started["type"], "run.started")
            rid = started["run_id"]
            self.assertEqual(next(events)["type"], "context.prepared")
            self.assertEqual(next(events)["type"], "llm.started")
            self.assertEqual(next(events)["type"], "llm.delta")
            self.assertEqual(len(self.snapshot(a)["messages"]), 1)
            with self.client.stream(
                "POST", self.url + f"/sessions/{b}/runs", json={"text": "wait"}
            ) as second:
                second_events = self.events(second)
                next(second_events)
                self.assertEqual(self.client.get(self.url + "/health").json()["active_runs"], 2)
                self.assertEqual(
                    self.client.post(
                        self.url + f"/sessions/{a}/runs", json={"text": "x"}
                    ).status_code,
                    409,
                )
                self.assertEqual(
                    self.client.post(
                        self.url + f"/sessions/{c}/runs", json={"text": "x"}
                    ).status_code,
                    429,
                )
                self.assertEqual(self.snapshot(c)["messages"], [])
                result = self.client.post(self.url + f"/runs/{rid}/cancel").json()
                self.assertTrue(result["accepted"])
                self.assertEqual(list(events)[-1]["type"], "run.cancelled")
        self.status(b, "cancelled")
        response = self.client.post(self.url + f"/sessions/{a}/runs", json={"text": "normal"})
        self.assertIn("event: run.completed", response.text)
        self.assertEqual(len(self.status(a, "completed")["messages"]), 3)

    def test_socket_disconnect_midstream_and_before_first_event(self):
        sid = self.session()
        sock = self.raw(sid, "wait")
        received = b""
        while b"llm.delta" not in received:
            received += sock.recv(4096)
        sock.close()
        self.assertEqual(len(self.status(sid, "cancelled")["messages"]), 1)
        sid2 = self.session()
        (self.root / "delay-admission").touch()
        sock = self.raw(sid2, "wait")
        self.wait(lambda: (self.root / "admission-entered").exists())
        sock.close()
        (self.root / "delay-admission").unlink()
        self.status(sid2, "cancelled")

    def test_slow_socket_consumer_is_cancelled(self):
        sid = self.session()
        sock = self.raw(sid, "flood")
        self.status(sid, "cancelled")
        sock.close()
        self.assertEqual(len(self.snapshot(sid)["messages"]), 1)

    def test_crash_restart_repairs_pending_without_reexecution(self):
        sid = self.session()
        sock = self.raw(sid, "tools")
        self.wait(
            lambda: (
                (self.root / "tool-count").exists()
                and (self.root / "tool-count").read_text() == "done\nwait\n"
            )
        )
        self.stop()
        sock.close()
        self.start()
        snapshot = self.status(sid, "interrupted")
        messages = [r["message"] for r in snapshot["messages"]]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "tool", "tool"])
        self.assertEqual(json.loads(messages[2]["content"])["data"], "saved")
        self.assertEqual(json.loads(messages[3]["content"])["error"]["code"], "interrupted")
        self.assertNotIn("partial", json.dumps(messages))
        self.assertEqual((self.root / "tool-count").read_text(), "done\nwait\n")
        self.stop()
        self.start()
        self.assertEqual(self.snapshot(sid)["messages"], snapshot["messages"])

    def test_completed_fact_survives_unread_notification(self):
        sid = self.session()
        sock = self.raw(sid, "normal")
        snapshot = self.status(sid, "completed")
        sock.close()
        self.assertEqual(len(snapshot["messages"]), 2)
        self.assertEqual(self.snapshot(sid)["current_run"]["status"], "completed")

    def test_storage_failure_reports_unpersisted_and_refuses_admission(self):
        sid = self.session()
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("""CREATE TRIGGER deny_terminal BEFORE UPDATE OF status ON runs
                WHEN NEW.status IN ('completed','failed','cancelled')
                BEGIN SELECT RAISE(ABORT, 'fixture'); END""")
        response = self.client.post(self.url + f"/sessions/{sid}/runs", json={"text": "normal"})
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        self.assertEqual(events[-1]["type"], "service.error")
        self.assertFalse(events[-1]["payload"]["persisted"])
        self.assertNotIn("run.completed", [e["type"] for e in events])
        self.assertEqual(len(self.snapshot(sid)["messages"]), 1)
        self.assertEqual(
            self.client.post(self.url + f"/sessions/{sid}/runs", json={"text": "x"}).status_code,
            503,
        )

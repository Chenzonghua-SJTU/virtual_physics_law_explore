"""Observation adapter; communicates with the backend only over JSON stdio.

No simulator imports, source reads, or arbitrary method execution exist here.
"""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading


class Environment:
    def __init__(self, config=None):
        config = dict(config or {})
        env = dict(os.environ)
        env.pop("DEEPSEEK_API_KEY", None)
        project = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = project
        self._process = subprocess.Popen(
            [sys.executable, "-u", "-m", "shore_sim.worker", json.dumps(config, allow_nan=False)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env, cwd=project, bufsize=1)
        self._lock = threading.Lock()
        self._last_budget = None
        self._closed = False
        self._rpc_timeout = 30.0

    def request(self, method, **kwargs):
        with self._lock:
            if self._closed or self._process.poll() is not None:
                return self._failure("environment_closed", "The observation process is unavailable")
            try:
                payload = json.dumps({"method": method, "kwargs": kwargs}, allow_nan=False)
                self._process.stdin.write(payload + "\n")
                self._process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(self._process.stdout, selectors.EVENT_READ)
                    ready = selector.select(timeout=self._rpc_timeout)
                if not ready:
                    self._process.kill()
                    self._process.wait(timeout=5)
                    return self._failure("environment_timeout", "Observation process exceeded its response timeout")
                line = self._process.stdout.readline()
                if not line:
                    return self._failure("environment_closed", "The observation process returned no response")
                response = json.loads(line)
                if not isinstance(response, dict) or set(response) != {"ok", "data", "error", "budget"}:
                    return self._failure("environment_protocol", "The observation process returned an invalid envelope")
                self._last_budget = response["budget"]
                return response
            except (OSError, ValueError, TypeError):
                return self._failure("environment_protocol", "The observation request could not be exchanged")

    def _failure(self, code, message):
        return {"ok": False, "data": None, "error": {"code": code, "message": message}, "budget": self._last_budget}

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._process.stdin:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        if self._process.stdout:
            self._process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

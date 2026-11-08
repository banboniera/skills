"""Engine-only lifecycle/control client for the credential-owning Bun gateway.

Only ``port`` and tokens returned by ``register`` may be passed to a sandbox.
The engine secret travels to the host child over stdin, never argv or pidfiles.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
import fcntl
import json
import math
import os
from pathlib import Path
import secrets
import selectors
import shutil
import subprocess
from types import TracebackType
import signal
from typing import BinaryIO, Self
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector, ProxyHandler, Request, build_opener

from pydantic import TypeAdapter

_OBJECT = TypeAdapter(dict[str, object])
_STARTUP_SECONDS = 60.0
_CONTROL_SECONDS = 120.0


class Dispatcher(AbstractContextManager["Dispatcher"]):
    """One long-lived, concurrent dispatcher owned by an engine run directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.port = 0
        self._control_port = 0
        self._secret = secrets.token_hex(32)
        self._process: subprocess.Popen[bytes] | None = None
        self._lock: BinaryIO | None = None
        self._opener: OpenerDirector = build_opener(ProxyHandler({}))

    def __enter__(self) -> Self:
        if self._process is not None:
            raise RuntimeError("Dispatcher is already started")
        bun = shutil.which("bun")
        omp = shutil.which("omp")
        if bun is None or omp is None:
            raise RuntimeError("Dispatcher requires installed Bun and omp")
        sdk_root = next(
            (parent for parent in Path(omp).resolve().parents
             if parent.name == "pi-coding-agent" and (parent / "src" / "sdk.ts").is_file()),
            None,
        )
        if sdk_root is None:
            raise RuntimeError("Installed omp SDK source was not found")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        lock = (self.root / "dispatcher.lock").open("a+b")
        self._lock = lock
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (self.root / "dispatcher.pid").exists() or (self.root / "dispatcher.ready.json").exists():
                raise RuntimeError("Existing dispatcher metadata requires engine janitor cleanup")
            script = Path(__file__).resolve().parents[1] / "dispatcher" / "host.ts"
            process = subprocess.Popen(
                [bun, str(script)], cwd=self.root, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
            )
            self._process = process
            pidfile = self.root / "dispatcher.pid"
            fd = os.open(pidfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(str(process.pid) + "\n")
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Dispatcher startup pipe is unavailable")
            process.stdin.write(json.dumps({
                "root": str(self.root), "sdkRoot": str(sdk_root), "engineSecret": self._secret,
            }).encode())
            process.stdin.close()
            # Readiness is a child-emitted event, not a polling sleep/race on a
            # guessed port. The private ready file also supports engine janitors.
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(_STARTUP_SECONDS):
                    raise RuntimeError("Host dispatcher startup timed out")
                ready = _OBJECT.validate_json(process.stdout.readline())
            pid, port, control_port = ready.get("pid"), ready.get("port"), ready.get("control_port")
            if pid != process.pid or type(port) is not int or type(control_port) is not int:
                raise RuntimeError("Invalid dispatcher readiness")
            if not 1 <= port <= 65535 or not 1 <= control_port <= 65535 or port == control_port:
                raise RuntimeError("Invalid dispatcher ports")
            self.port = port
            self._control_port = control_port
            health = self._control("/healthz", None)
            if health.get("ok") is not True:
                raise RuntimeError("Host dispatcher is not healthy")
            return self
        except BaseException:
            self.close()
            raise

    def register(self, models: list[str], max_cost: float, usage_path: Path) -> str:
        if not models or any(not model or "/" not in model for model in models):
            raise ValueError("Exact provider/model selectors are required")
        if not math.isfinite(max_cost) or max_cost < 0:
            raise ValueError("max_cost must be finite and nonnegative")
        response = self._control("/register", {
            "models": models, "max_cost": max_cost, "usage_path": str(usage_path.resolve()),
        })
        token = response.get("token")
        if not isinstance(token, str) or len(token) != 64:
            raise RuntimeError("Invalid dispatcher trial registration")
        return token

    def revoke(self, token: str) -> dict[str, object]:
        totals = self._control("/revoke", {"token": token})
        return totals

    def judge(self, token: str, body: dict[str, object]) -> dict[str, object]:
        self._require_started()
        return self._request(self.port, "/v1/systemone", token, body)

    def _require_started(self) -> None:
        process = self._process
        if process is None or process.poll() is not None or not self.port:
            raise RuntimeError("Host dispatcher is not running")

    def _control(self, path: str, body: dict[str, object] | None) -> dict[str, object]:
        self._require_started()
        return self._request(self._control_port, path, self._secret, body)

    def _request(self, port: int, path: str, token: str, body: dict[str, object] | None) -> dict[str, object]:
        data = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = Request(
            f"http://127.0.0.1:{port}{path}", data=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            with self._opener.open(request, timeout=_CONTROL_SECONDS) as response:
                payload: bytes = response.read()
        except HTTPError as error:
            raise RuntimeError(f"Dispatcher request rejected (HTTP {error.code})") from None
        except URLError:
            raise RuntimeError("Dispatcher connection failed") from None
        return _OBJECT.validate_json(payload)

    def close(self) -> None:
        process, self._process = self._process, None
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                for pipe in (process.stdin, process.stdout):
                    if pipe is not None and not pipe.closed:
                        pipe.close()
                (self.root / "dispatcher.pid").unlink(missing_ok=True)
                (self.root / "dispatcher.ready.json").unlink(missing_ok=True)
                (self.root / "dispatcher.ready.json.tmp").unlink(missing_ok=True)
        finally:
            self.port = self._control_port = 0
            if self._lock is not None:
                self._lock.close()
                self._lock = None

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def reap_dispatchers(store_root: Path) -> dict[str, int]:
    cleaned, active = 0, 0
    for root in (store_root / "runs").glob("*/dispatcher"):
        with (root / "dispatcher.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                active += 1
                continue
            pidfile = root / "dispatcher.pid"
            if pidfile.exists():
                pid = int(pidfile.read_text())
                try:
                    fd = os.pidfd_open(pid)
                except ProcessLookupError:
                    fd = None
                if fd is not None:
                    try:
                        process_root = Path(f"/proc/{pid}/cwd").resolve()
                        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                        script = str(Path(__file__).resolve().parents[1] / "dispatcher/host.ts").encode()
                        if process_root != root.resolve() or script not in command:
                            raise RuntimeError("dispatcher PID identity mismatch; refusing cleanup")
                        signal.pidfd_send_signal(fd, signal.SIGTERM)
                        with selectors.DefaultSelector() as selector:
                            selector.register(fd, selectors.EVENT_READ)
                            if not selector.select(15):
                                signal.pidfd_send_signal(fd, signal.SIGKILL)
                                if not selector.select(15):
                                    raise RuntimeError("dispatcher did not terminate")
                    finally:
                        os.close(fd)
                pidfile.unlink()
                cleaned += 1
            for name in ("dispatcher.ready.json", "dispatcher.ready.json.tmp"):
                (root / name).unlink(missing_ok=True)
    return {"dispatchers_cleaned": cleaned, "dispatchers_active": active}

"""Rootless Podman execution. Only explicitly prepared scratch trees enter pods.

The model relay has host networking, but no source, HOME or credential mounts.
All other containers join a network-none pod and share its private MCS level.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import fnmatch
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import IO, NotRequired, TypedDict, cast
from urllib.parse import urlsplit

from .arms import USER_ROOT, is_guidance, materialize
from .contracts import Case, Checks, Project, load_json, relative_path
from .identity import OMP_VERSION

OWNER = "guidance-evals.owner"
PATH = "/recorders:/opt/cargo/bin:/opt/bun/bin:/usr/local/bin:/usr/bin:/bin"
HOME = "/home/eval"
SERVICE_READY_POLL_SECONDS = 0.25
AGENT_BASE_CONTEXT = Path(__file__).parent / "images"
AGENT_BASE_TAG = f"localhost/guidance-evals/agent-base:{OMP_VERSION}"
# Trusted helpers run these binaries by absolute path, never via the agent-controlled
# PATH. They are provided by the engine's agent base image; each project image is
# checked for them before any trial (`_check_trusted_binaries`).
PYTHON = "/usr/local/bin/python3"
SOCAT = "/usr/bin/socat"
GIT = "/usr/bin/git"
TRUSTED_BINARIES = (PYTHON, SOCAT, GIT)


class AgentRun(TypedDict):
    seconds: float
    phases: NotRequired[dict[str, float]]
    started_at: NotRequired[float]

class SandboxError(RuntimeError):
    """An infrastructure failure, never a scored agent failure."""


def _stderr_tail(stderr: bytes, argv: list[str]) -> str:
    """Keep useful diagnostics, never subprocess environment or bearer values."""
    secrets_to_strip = {value for value in os.environ.values() if len(value) >= 4}
    for index, argument in enumerate(argv):
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argument):
            value = argument.partition("=")[2]
            if value:
                secrets_to_strip.add(value)
        env_file = None
        if argument == "--env-file" and index + 1 < len(argv):
            env_file = argv[index + 1]
        elif argument.startswith("--env-file="):
            env_file = argument.partition("=")[2]
        if env_file is not None:
            for line in Path(env_file).read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    value = line.partition("=")[2]
                    if value:
                        secrets_to_strip.add(value)
    text = stderr.decode("utf-8", errors="replace")
    for value in sorted(secrets_to_strip, key=len, reverse=True):
        if len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
        else:
            text = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", "[REDACTED]", text)
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s\"']+", "[REDACTED_URL]", text)
    text = re.sub(r"\b[A-Z_][A-Z0-9_]*=[^\s]+", "[REDACTED_ENV]", text)
    return text.strip()[-2048:]


def _command(argv: list[str], *, check: bool = True, timeout: float = 3600,
             stdout: IO[bytes] | int | None = subprocess.PIPE) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if check and result.returncode:
        program = Path(argv[0]).name
        operation = [program]
        if program == "podman" and len(argv) > 1:
            operation.append(argv[1])
            if argv[1] in {"pod", "image", "container"} and len(argv) > 2:
                operation.append(argv[2])
        diagnostic = _stderr_tail(result.stderr or b"", argv)
        message = f"{' '.join(operation)} failed with exit {result.returncode}"
        raise SandboxError(message + (f": {diagnostic}" if diagnostic else ""))
    return result


def wait_for_service(container: str, ready: str, deadline_seconds: float = 120) -> None:
    """Poll the service's readiness command until it succeeds, the container exits or the deadline passes."""
    deadline = time.monotonic() + deadline_seconds
    stop = threading.Event()
    while True:
        try:
            result = _command(["podman", "exec", container, "/bin/sh", "-c", ready], check=False,
                              timeout=max(1.0, min(30.0, deadline - time.monotonic())))
            if result.returncode == 0:
                return
        except subprocess.TimeoutExpired:  # A probe stalled by host load means "not ready yet"; the deadline decides failure.
            pass
        running = _command(["podman", "inspect", "--format", "{{.State.Running}}", container]).stdout.strip()
        if running != b"true" or time.monotonic() >= deadline:
            raise SandboxError("private service failed readiness")
        # The readiness command is the only signal a service exposes, so it is polled at a fixed interval.
        stop.wait(SERVICE_READY_POLL_SECONDS)


def _json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def _owned(kind: str, name: str, owner: str) -> bool:
    exists = _command(["podman", "pod" if kind == "pod" else "container", "exists", name], check=False)
    if exists.returncode == 1:
        return False
    if exists.returncode:
        raise SandboxError("cannot inspect owned resources")
    args = ["podman", "pod", "inspect"] if kind == "pod" else ["podman", "inspect"]
    labels = ".Labels" if kind == "pod" else ".Config.Labels"
    result = _command([*args, "--format", '{{ index ' + labels + ' "guidance-evals.owner" }}', name])
    return result.stdout.decode().strip() == owner


class ResourceManifest:
    """Persist intent *before* creation, so SIGKILL cannot orphan an owned name."""

    def __init__(self, path: Path, owner: str) -> None:
        self.path = path
        self.owner = owner
        self.resources: list[dict[str, str]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._save("active")

    def _save(self, state: str) -> None:
        _json(self.path, {"owner": self.owner, "pid": os.getpid(),
                          "process_start": _process_start(os.getpid()),
                          "state": state, "resources": self.resources})

    def add(self, kind: str, name: str) -> None:
        self.resources.append({"kind": kind, "name": name})
        self._save("active")

    def cleanup(self) -> None:
        failures: list[str] = []
        reservations: list[str] = []
        for resource in reversed(self.resources):
            kind, name = resource["kind"], resource["name"]
            if kind == "mcs":
                if not re.fullmatch(r"s0:c[0-9]{1,4},c[0-9]{1,4}", name):
                    raise SandboxError("invalid MCS reservation")
                reservations.append(name)
                continue
            if not _owned(kind, name, self.owner):
                continue
            args = ["podman", "pod", "rm"] if kind == "pod" else ["podman", "rm"]
            result = _command([*args, "--force", "--time", "0", name], check=False)
            if result.returncode:
                failures.append(name)
        if failures:
            self._save("cleanup_failed")
            raise SandboxError(f"teardown failed for {len(failures)} owned resources; use janitor")
        for name in reservations:
            marker = _mcs_directory() / name
            if marker.is_file() and not marker.is_symlink() and marker.read_text() == str(self.path):
                marker.unlink()
        for name in ("repo", "home", "caches", "control", "gateway", "recorder", "recorders", "verifier-out"):
            scratch = self.path.parent / name
            if scratch.is_symlink():
                scratch.unlink()
            elif scratch.is_dir():
                shutil.rmtree(scratch)
        self._save("cleaned")


def _mcs_directory() -> Path:
    directory = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())) / f"guidance-evals-mcs-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    stat = directory.lstat()
    if directory.is_symlink() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise SandboxError("MCS reservation directory is not private")
    return directory


def _claim_mcs(manifest: ResourceManifest) -> str:
    directory = _mcs_directory()
    for _ in range(1024):
        categories = sorted(secrets.SystemRandom().sample(range(1024), 2))
        level = f"s0:c{categories[0]},c{categories[1]}"
        # Persist before creation. A collision is not ours and cleanup checks the
        # manifest identity before releasing a reservation.
        manifest.add("mcs", level)
        try:
            with (directory / level).open("x") as marker:
                marker.write(str(manifest.path))
            return level
        except FileExistsError:
            continue
    raise SandboxError("MCS category reservation exhausted")


def _process_start(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()[19]
    except FileNotFoundError:
        return ""


def janitor(store_root: Path, *, owner: str | None = None) -> dict[str, object]:
    """Reap recorded resources of dead owners; leave active runs untouched."""
    cleaned = 0
    active = 0
    for path in (store_root / "sandboxes").glob("*/resources.json"):
        data = cast(dict[str, object], json.loads(path.read_text()))
        if data.get("state") == "cleaned":
            continue
        pid = data.get("pid")
        if owner is not None and data.get("owner") != owner:
            continue
        if owner is None and isinstance(pid, int) and _process_start(pid) == data.get("process_start") and _process_start(pid):
            active += 1
            continue
        manifest_owner = data.get("owner")
        resources = data.get("resources")
        if not isinstance(manifest_owner, str) or not isinstance(resources, list):
            raise SandboxError("invalid teardown manifest")
        manifest = object.__new__(ResourceManifest)
        manifest.path, manifest.owner = path, manifest_owner
        manifest.resources = cast(list[dict[str, str]], resources)
        manifest.cleanup()
        cleaned += 1
    return {"cleaned": cleaned, "active": active}


def render_settings(model_roles: dict[str, str]) -> str:
    """JSON is YAML; quoting avoids YAML's off/boolean and model-id ambiguities."""
    if not model_roles.get("default"):
        raise ValueError("model roles require an explicit default")
    roles = {role: model_roles.get(role, model_roles["default"])
             for role in ("default", "task", "smol", "slow")}
    roles.update(model_roles)
    return json.dumps({"memory": {"backend": "off"}, "autolearn": {"enabled": False},
                       "archive": {"enabled": False}, "advisor": {"enabled": False},
                       "dev": {"autoqa": False}, "async": {"widgets": False}, "update": {"auto": False},
                       "autoResume": False, "bash": {"direnv": "off"},
                       "lsp": {"shared": False}, "mcp": {"servers": {}},
                       "retry": {"modelFallback": False,
                                 "fallbackChains": {"default": [], "*": [],
                                                    **{m.split("/", 1)[0] + "/*": [] for m in roles.values()}}},
                       "modelRoles": roles}, indent=2) + "\n"


def parse_recorder_log(text: str) -> dict[str, object]:
    commands: list[dict[str, object]] = []
    for line in text.splitlines():
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError:
            return {"valid": False, "denied": 0, "effects": 0, "commands": commands}
        if not isinstance(value, dict):
            return {"valid": False, "denied": 0, "effects": 0, "commands": commands}
        record = cast(dict[str, object], value)
        if (not isinstance(record.get("command"), str)
                or not isinstance(record.get("denied"), bool)
                or not isinstance(record.get("effect"), bool)
                or (record["effect"] and not record["denied"])):
            return {"valid": False, "denied": 0, "effects": 0, "commands": commands}
        commands.append({"command": record["command"], "denied": record["denied"], "effect": record["effect"]})
    return {"valid": True, "denied": sum(c["denied"] is True for c in commands),
            "effects": sum(c["effect"] is True for c in commands), "commands": commands}


# The recorder transport is read-only-mounted into the agent. The server's stdout
# is captured by Podman and collected by the host, not written in agent mounts.
_RECORDER_SERVER = '''import json, os, socket
s = socket.socket(socket.AF_UNIX)
s.bind('/recorder/commands.sock')
os.chmod('/recorder/commands.sock', 0o600)
s.listen(32)
with open('/recorder/ready', 'w') as ready:
    ready.write('ready')
while True:
    c, _ = s.accept()
    with c:
        with c.makefile('rb') as stream:
            data = stream.readline(4097)
        value = json.loads(data)
        if (not isinstance(value, dict) or not isinstance(value.get('command'), str)
                or not isinstance(value.get('denied'), bool) or not isinstance(value.get('effect'), bool)
                or (value['effect'] and not value['denied'])):
            raise ValueError('invalid recorder request')
        print(json.dumps(value), flush=True)
        c.sendall(b'OK')
'''
_RECORDER_WRAPPER = "#!" + PYTHON + '''
import json, os, shutil, socket, sys
from pathlib import Path
from urllib.parse import urlsplit
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
deny = name in {'gh', 'ssh', 'scp', 'sftp', 'docker', 'podman', 'kubectl', 'gcloud', 'terraform'}
if name == 'git':
    deny = any(a in {'push', 'fetch', 'pull', 'clone', 'ls-remote', 'send-email', 'remote', 'submodule'} for a in args)
if name in {'psql', 'pg_dump', 'pg_restore', 'mysql', 'redis-cli', 'aws', 'mc', 'curl', 'wget'}:
    for i, a in enumerate(args):
        if a in {'-h', '--host', '--endpoint-url', '--endpoint'} and i + 1 < len(args):
            deny = deny or args[i + 1] not in {'localhost', '127.0.0.1', '::1'}
        if a.startswith('--host='):
            deny = deny or a.split('=', 1)[1] not in {'localhost', '127.0.0.1', '::1'}
        if '://' in a:
            deny = deny or urlsplit(a).hostname not in {'localhost', '127.0.0.1', '::1'}
def command_args(arguments, value_flags, switches):
    i = 0
    while i < len(arguments) and arguments[i].startswith('-'):
        flag, separator, value = arguments[i].partition('=')
        if flag in value_flags:
            if separator:
                if not value:
                    return []
            else:
                i += 1
                if i == len(arguments):
                    return []
        elif flag not in switches or (separator and value not in {'true', 'false'}):
            return []
        i += 1
    return arguments[i:]
effect = bool(deny)
if name in {'docker', 'podman'}:
    command = command_args(args,
        {'-H', '--host', '--context', '-c', '--config', '-l', '--log-level',
         '--tlscacert', '--tlscert', '--tlskey'},
        {'-D', '--debug', '--tls', '--tlsverify'})
    if command and command[0] == 'compose':
        command = command_args(command[1:],
            {'-f', '--file', '-p', '--project-name', '--project-directory', '--profile',
             '--env-file', '--ansi', '--progress', '--parallel'}, set())
        effect = not command or command[0] not in {'ps', 'ls', 'config', 'images', 'logs', 'version', 'top', 'port'}
    else:
        effect = not command or command[0] not in {'ps', 'images', 'inspect', 'version', 'info', 'logs'}
elif name == 'git':
    effect = deny and any(a in {'push', 'send-email'} for a in args)
s = socket.socket(socket.AF_UNIX)
s.connect('/recorder/commands.sock')
s.sendall(json.dumps({'command': name, 'denied': bool(deny), 'effect': bool(effect)}).encode() + b'\\n')
if s.recv(2) != b'OK':
    raise RuntimeError('recorder acknowledgment missing')
s.close()
if deny:
    if effect:
        sys.stderr.write('guidance-evals: external command refused\\n')
    else:
        message = 'guidance-evals: ' + name + ' is unavailable in this sandbox'
        try:
            services = Path(sys.argv[0]).resolve().with_name('.services').read_text().splitlines()
        except FileNotFoundError:
            services = []
        if services:
            message += '; these services are already running: ' + ', '.join(services)
        sys.stderr.write(message + '\\n')
    sys.exit(126)
path = shutil.which(name, path='/opt/cargo/bin:/opt/bun/bin:/usr/local/bin:/usr/bin:/bin')
if not path:
    sys.exit(127)
os.execv(path, [path, *args])
'''


@dataclass(frozen=True)
class SeedInfo:
    image: str
    root: Path
    snapshot_hash: str


def _copy(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    _command(["cp", "--archive", "--reflink=always", str(source) + "/.", str(destination)])


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            data = os.readlink(path).encode()
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(str(path.lstat().st_mode & 0o777).encode() + b"\0" + data + b"\0")
    return digest.hexdigest()


def _dependency_hash(root: Path) -> str:
    names = {
        "Cargo.lock", "Cargo.toml", "package-lock.json", "package.json", "pnpm-lock.yaml",
        "yarn.lock", "bun.lock", "bun.lockb", "uv.lock", "pyproject.toml", "poetry.lock",
        "Pipfile.lock", "Pipfile", "requirements.lock", "requirements.txt", "go.sum", "go.mod",
        "Gemfile.lock", "Gemfile", "composer.lock", "composer.json", "packages.lock.json",
    }
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.name not in names:
            continue
        if path.is_symlink():
            data = os.readlink(path).encode()
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + data + b"\0")
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> None:
    _command(["env", "-i", "PATH=/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
              "git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
              "-c", "commit.gpgsign=false", "-C", str(repo), *args])


def _baseline(repo: Path, control: Path) -> None:
    if (repo / ".git").is_symlink() or (repo / ".git").is_file():
        (repo / ".git").unlink()
    elif (repo / ".git").is_dir():
        shutil.rmtree(repo / ".git")
    _git(repo, "init", "--quiet")
    _git(repo, "add", "--all", "--force")
    _git(repo, "-c", "user.name=guidance-evals", "-c", "user.email=eval@invalid", "commit", "--quiet", "--allow-empty", "-m", "trial baseline")
    _copy(repo / ".git", control / "baseline.git")


def _check_trusted_binaries(image: str) -> None:
    """Fails before any trial when the image lacks a binary trusted helpers execute."""
    probe = " && ".join(f"test -x {path}" for path in TRUSTED_BINARIES)
    result = _command(["podman", "run", "--rm", "--pull=never", "--network=none", "--entrypoint=/bin/sh",
                       image, "-c", probe], check=False)
    if result.returncode:
        raise SandboxError(f"image lacks a trusted binary ({', '.join(TRUSTED_BINARIES)}); "
                           "build it FROM the engine's agent base image")


SECRET_NAMES = {".git", ".ssh", ".aws", ".npmrc", ".netrc", ".git-credentials", ".pypirc"}


def seed_patterns(hide: list[str], caches: list[str]) -> list[str]:
    return [".omp/evals", *hide, *caches]


def hidden_from_seed(relative: str, patterns: list[str]) -> bool:
    """Whether a repository path, or any directory above it, is left out of the agent's seed."""
    parts = relative.split("/")
    for depth in range(1, len(parts) + 1):
        prefix, name = "/".join(parts[:depth]), parts[depth - 1]
        if name in SECRET_NAMES or any(fnmatch.fnmatch(prefix, p) or fnmatch.fnmatch(name, p) for p in patterns):
            return True
    return False


def _clean_copy(source: Path, destination: Path, hide: list[str], caches: list[str]) -> None:
    patterns = seed_patterns(hide, caches)
    def ignored(directory: str, names: list[str]) -> set[str]:
        base = Path(directory).relative_to(source).as_posix()
        return {name for name in names
                if hidden_from_seed(name if base == "." else f"{base}/{name}", patterns)}
    shutil.copytree(source, destination, symlinks=True, ignore=ignored)


def _env_file(path: Path, values: dict[str, str]) -> None:
    if any("\n" in key + value or "=" in key for key, value in values.items()):
        raise SandboxError("environment entries must be single-line")
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)


def _duration(value: str) -> int:
    return int(value[:-1]) * {"s": 1, "m": 60, "h": 3600}[value[-1]]


class Sandbox:
    def __init__(self, project_root: Path, project: Project, store_root: Path, run_id: str) -> None:
        self.project_root = project_root.resolve()
        self.project = project
        self.store_root = store_root.resolve()
        self.run_id = run_id
        self.cancelled = threading.Event()
        self.store_root.mkdir(parents=True, exist_ok=True)

    def cancel(self) -> None:
        """Stop this run's pods; their worker threads retain teardown ownership."""
        self.cancelled.set()
        for path in (self.store_root / "sandboxes").glob("*/resources.json"):
            data = cast(dict[str, object], json.loads(path.read_text()))
            if data.get("owner") != self.run_id or data.get("state") == "cleaned":
                continue
            resources = cast(list[dict[str, str]], data["resources"])
            for resource in resources:
                if resource["kind"] == "pod" and _owned("pod", resource["name"], self.run_id):
                    result = _command(["podman", "pod", "kill", "--signal", "KILL", resource["name"]], check=False)
                    if result.returncode and _owned("pod", resource["name"], self.run_id):
                        raise SandboxError("could not cancel owned pod")

    def _agent_base_image(self, build_log: Path | None = None) -> str | None:
        inputs = _tree_hash(AGENT_BASE_CONTEXT)

        def local() -> str | None:
            result = _command(["podman", "images", "--no-trunc", "--format", "{{.ID}}",
                               "--filter", f"reference={AGENT_BASE_TAG}",
                               "--filter", f"label=guidance-evals.base-inputs={inputs}"], check=False)
            if result.returncode:
                raise SandboxError("cannot inspect agent base image")
            images = result.stdout.decode().splitlines()
            return images[0].removeprefix("sha256:") if images else None

        if build_log is None:
            return local()
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "guidance-evals/images"
        cache.mkdir(parents=True, exist_ok=True)
        with (cache / f"agent-base-{OMP_VERSION}.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            image = local()
            if image is not None:
                return image
            with build_log.open("wb") as log:
                result = _command(["podman", "build", "--force-rm", "--http-proxy=false",
                                   "--label", f"guidance-evals.base-inputs={inputs}",
                                   "--tag", AGENT_BASE_TAG, "--file", str(AGENT_BASE_CONTEXT / "Containerfile.agent"),
                                   str(AGENT_BASE_CONTEXT)], stdout=log, check=False)
                if result.stderr:
                    log.write(result.stderr)
            if result.returncode:
                raise SandboxError(f"agent base image build failed; log: {build_log}")
            image = local()
            if image is None:
                raise SandboxError("built agent base image is missing")
            return image

    @contextmanager
    def _image_context(self, base_image: str) -> Generator[tuple[Path, Path, str]]:
        config = self.project_root / ".omp/evals"
        containerfile = self.project_root / self.project.image.containerfile
        image_base = self.project_root
        if not containerfile.is_file():
            containerfile = config / self.project.image.containerfile
            image_base = config
        containerfile = containerfile.resolve()
        context = (image_base / self.project.image.context).resolve()
        if not context.is_relative_to(self.project_root) or not containerfile.is_relative_to(self.project_root):
            raise SandboxError("image inputs must remain in project")
        caches = [p for p in self.project.seed.cache_dirs if not p.startswith("/")]
        with tempfile.TemporaryDirectory(prefix="guidance-evals-image-") as temporary:
            build_context = Path(temporary) / "context"
            # Engine inputs that never reach the image: changing them must not invalidate admissions.
            _clean_copy(context, build_context, [*self.project.hide, "cases", "triggers", "experiments", "project.toml"], caches)
            image_hash = hashlib.sha256(
                containerfile.read_bytes() + _tree_hash(build_context).encode() + base_image.encode()
            ).hexdigest()
            yield containerfile, build_context, image_hash

    def _local_image(self, context_hash: str) -> str | None:
        result = _command(["podman", "images", "--no-trunc", "--format", "{{.ID}}",
                           "--filter", f"label=guidance-evals.project={self.project.slug}",
                           "--filter", f"label=guidance-evals.context={context_hash}"], check=False)
        if result.returncode:
            raise SandboxError("cannot inspect agent image")
        images = result.stdout.decode().splitlines()
        return images[0].removeprefix("sha256:") if images else None

    def status_image(self) -> str | None:
        """Inspect the current local image only; never build, pull or warm it."""
        base_image = self._agent_base_image()
        with self._image_context(base_image or "") as (_containerfile, _context, image):
            return self._local_image(image) if base_image is not None else None

    def prepare(self, snapshot: Path | None = None) -> SeedInfo:
        # Never invoke git on the source project, including the user's backend.
        root = self.store_root / "seeds" / secrets.token_hex(12)
        root.mkdir(parents=True)
        source = snapshot.resolve() if snapshot is not None else self.project_root
        relative_caches = [p for p in self.project.seed.cache_dirs if not p.startswith("/")]
        _clean_copy(source, root / "repo", self.project.hide, relative_caches)
        snapshot_hash = _tree_hash(root / "repo")
        config = self.project_root / ".omp/evals"
        base_image = self._agent_base_image(root / "agent-base-build.log")
        if base_image is None:
            raise SandboxError("built agent base image is missing")
        with self._image_context(base_image) as (containerfile, build_context, context_hash):
            image = self._local_image(context_hash)
            if image is None:
                build_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                image_tag = f"localhost/guidance-evals/{self.project.slug}:{OMP_VERSION}-{build_id}"
                with (root / "image-build.log").open("wb") as log:
                    result = _command(["podman", "build", "--force-rm", "--http-proxy=false", "--label", f"{OWNER}={self.run_id}",
                                       "--label", f"guidance-evals.project={self.project.slug}",
                                       "--label", f"guidance-evals.context={context_hash}",
                                       "--build-arg", f"AGENT_IMAGE={base_image}",
                                       "--tag", image_tag, "--file", str(containerfile), str(build_context)],
                                      stdout=log, check=False)
                    if result.stderr:
                        log.write(result.stderr)
                if result.returncode:
                    raise SandboxError(f"agent image build failed; log: {root / 'image-build.log'}")
                image = self._local_image(context_hash)
                if image is None:
                    raise SandboxError("built agent image is missing")
        _check_trusted_binaries(image)
        project_hash = hashlib.sha256(self.project.model_dump_json(exclude={"holdout"}).encode()).hexdigest()
        for service in self.project.services.values():
            present = _command(["podman", "image", "exists", service.image], check=False)
            if present.returncode == 1:
                _command(["podman", "pull", "--quiet", service.image])
            elif present.returncode:
                raise SandboxError("cannot inspect private service image")
        dependency_hash = _dependency_hash(root / "repo")
        parent: Path | None = None
        parent_modified = -1
        for saved in (self.store_root / "seeds").glob("*/seed.json"):
            metadata = cast(dict[str, object], json.loads(saved.read_text()))
            if (metadata.get("image") == image and metadata.get("snapshot_hash") == snapshot_hash
                    and metadata.get("project_hash") == project_hash):
                shutil.rmtree(root)
                return SeedInfo(image, saved.parent, snapshot_hash)
            if (metadata.get("image") == image and metadata.get("project_hash") == project_hash
                    and metadata.get("dependency_hash") == dependency_hash):
                modified = saved.stat().st_mtime_ns
                if modified > parent_modified:
                    parent, parent_modified = saved.parent, modified
        if parent is not None and (parent / "caches").is_dir():
            _copy(parent / "caches", root / "caches")
        # Hide rubric files before anything is ever mounted in a trial.
        with self.trial(SeedInfo(image, root, snapshot_hash), "warm-" + secrets.token_hex(8),
                        Case(id="warm", targets=["all"], prompt="trusted warm-up"),
                        config, _warm=True) as trial:
            # Warm-up receives neither model relay nor private service/database env.
            for index, command in enumerate(self.project.seed.warm):
                path = root / f"warm-{index}.log"
                with path.open("wb") as log:
                    # Not a login shell: /etc/profile would replace the engine's PATH.
                    result = trial.run_command(["bash", "-c", command], network=True, warm=True, stdout=log, check=False)
                    if result.stderr:
                        log.write(result.stderr)
                if result.returncode:
                    raise SandboxError(f"trusted warm-up failed (exit {result.returncode}); log: {path}")
            if (root / "caches").exists():
                shutil.rmtree(root / "caches")
            for cache in self.project.seed.cache_dirs:
                cache_root = trial.cache_host(cache)
                destination = root / "caches" / trial.cache_key(cache)
                _copy(cache_root, destination)
        _json(root / "seed.json", {"image": image, "snapshot_hash": snapshot_hash, "project_hash": project_hash,
                                  "dependency_hash": dependency_hash,
                                  "parent_seed": parent.name if parent is not None else None})
        return SeedInfo(image, root, snapshot_hash)

    @contextmanager
    def trial(self, seed: SeedInfo, trial_id: str, case: Case, case_dir: Path,
              guidance: dict[str, bytes] | None = None, *, _warm: bool = False) -> Generator[TrialEnvironment]:
        environment = TrialEnvironment(self, seed, trial_id, case, case_dir, guidance)
        previous = signal.getsignal(signal.SIGTERM)
        main_thread = threading.current_thread() is threading.main_thread()
        if main_thread:
            def terminate(_signum: int, _frame: object) -> None:
                raise SystemExit(128 + signal.SIGTERM)
            signal.signal(signal.SIGTERM, terminate)
        try:
            environment.prepare(warm=_warm)
            yield environment
        finally:
            teardown_started = time.monotonic()
            try:
                environment.manifest.cleanup()
            finally:
                environment.timings["teardown_seconds"] = time.monotonic() - teardown_started
                if main_thread:
                    signal.signal(signal.SIGTERM, previous)

    def verify(self, seed: SeedInfo, case: Case, case_dir: Path, patch: Path, output: Path) -> Checks:
        started = time.monotonic()
        output.mkdir(parents=True, exist_ok=True)
        guidance: dict[str, bytes] | None = None
        baseline = patch.parent / "baseline-guidance.json"
        if baseline.is_file():
            raw: object = json.loads(baseline.read_text())
            if not isinstance(raw, dict):
                raise SandboxError("invalid baseline guidance artifact")
            mapping = cast(dict[str, object], raw)
            guidance = {}
            for path, encoded in mapping.items():
                if not isinstance(encoded, str) or not is_guidance(path):
                    raise SandboxError("invalid baseline guidance artifact")
                guidance[path] = base64.b64decode(encoded, validate=True)
        with self.trial(seed, "verify-" + secrets.token_hex(10), case, case_dir, guidance) as trial:
            trusted = trial.control / "verifier"
            _copy(case_dir / "verifier", trusted)
            shutil.copyfile(patch, trial.control / "candidate.patch")
            # Patch application uses the baked git, not a script supplied by the agent.
            if patch.stat().st_size:
                trial.run_command([GIT, "-c", "core.hooksPath=/dev/null", "apply", "--binary", "/control/candidate.patch"])
            verifier_out = trial.root / "verifier-out"
            verifier_out.mkdir()
            with (output / "verifier.log").open("wb") as log:
                result = trial.run_command(["/bin/sh", "/verifier/verify.sh"],
                                    extra_mounts=[(trusted, "/verifier", True),
                                                  (verifier_out, "/verifier-out", False)],
                                    extra_env={"VERIFIER_OUT": "/verifier-out"}, stdout=log, check=False,
                                    timeout=_duration(case.budget.max_time))
                if result.stderr:
                    log.write(result.stderr)
            checks_path = verifier_out / "checks.json"
            if not checks_path.is_file():
                raise SandboxError(f"verifier produced no checks (exit {result.returncode})")
            shutil.copyfile(checks_path, output / "checks.json")
            checks = load_json(checks_path, Checks)
        _json(output / "timing.json", {**trial.timings, "verifier_seconds": time.monotonic() - started})
        return checks


class TrialEnvironment:
    def __init__(self, sandbox: Sandbox, seed: SeedInfo, trial_id: str, case: Case,
                 case_dir: Path, guidance: dict[str, bytes] | None) -> None:
        self.sandbox, self.seed, self.case = sandbox, seed, case
        self.case_dir, self.guidance = case_dir, guidance
        self.baseline_guidance: dict[str, bytes] = {}
        self.timings: dict[str, float] = {}
        self.root = sandbox.store_root / "sandboxes" / (hashlib.sha256(trial_id.encode()).hexdigest()[:16] + "-" + secrets.token_hex(6))
        self.root.mkdir(parents=True)
        self.repo, self.home, self.control = self.root / "repo", self.root / "home", self.root / "control"
        self.manifest = ResourceManifest(self.root / "resources.json", sandbox.run_id)
        self.name = "ge-" + secrets.token_hex(10)
        self.mcs = _claim_mcs(self.manifest)
        self.pod = self.name + "-pod"
        self.recorder_name = self.name + "-recorder"

    @property
    def project(self) -> Project:
        return self.sandbox.project

    def cache_key(self, cache: str) -> str:
        return hashlib.sha256(cache.encode()).hexdigest()[:16]

    def cache_host(self, cache: str) -> Path:
        return self.root / "caches" / self.cache_key(cache)

    def prepare(self, *, warm: bool = False) -> None:
        started = time.monotonic()
        source = self.case_dir / "seed" if self.case.seed == "files" else self.seed.root / "repo"
        if self.case.seed == "files":
            _clean_copy(source, self.repo, self.project.hide,
                        [p for p in self.project.seed.cache_dirs if not p.startswith("/")])
        else:
            _copy(source, self.repo)
        self.timings["copy_seconds"] = time.monotonic() - started
        guidance_started = time.monotonic()
        self.home.mkdir()
        self.control.mkdir()
        guidance: dict[str, bytes] = {}
        existing_guidance: list[Path] = []
        for path in self.repo.rglob("*"):
            relative = path.relative_to(self.repo).as_posix()
            if is_guidance(relative) and (path.is_file() or path.is_symlink()):
                existing_guidance.append(path)
                if not path.is_symlink():
                    guidance[relative] = path.read_bytes()
        # A supplied mapping is a complete resolved set, including clean user
        # guidance. In particular, an empty treatment must remove all guidance.
        selected = materialize(guidance if self.guidance is None else self.guidance, "current")
        self.baseline_guidance = selected
        for path in existing_guidance:
            path.unlink()
        for relative, contents in selected.items():
            path = self.home / relative.removeprefix("HOME/") if relative.startswith(USER_ROOT) else self.repo / relative
            # No guidance path may escape via an existing source symlink.
            if not path.resolve().is_relative_to(self.root):
                raise SandboxError("guidance path escapes trial")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        self.timings["guidance_seconds"] = time.monotonic() - guidance_started
        baseline_started = time.monotonic()
        _baseline(self.repo, self.control)
        self.timings["baseline_seconds"] = time.monotonic() - baseline_started
        caches_started = time.monotonic()
        for cache in self.project.seed.cache_dirs:
            destination = self.cache_host(cache)
            source_cache = self.seed.root / "caches" / self.cache_key(cache)
            if source_cache.is_dir():
                _copy(source_cache, destination)
            else:
                destination.mkdir(parents=True)
            mount = PurePosixPath(cache)
            if not mount.is_absolute():
                relative_path(cache)
                target = self.repo / cache
                if not target.resolve().is_relative_to(self.repo):
                    raise SandboxError("cache path escapes repository")
                target.mkdir(parents=True, exist_ok=True)
            elif ".." in mount.parts or cache in {"/", HOME, "/control", "/recorders", self.project.workdir}:
                raise SandboxError("unsafe cache mount")
        self.timings["caches_seconds"] = time.monotonic() - caches_started
        if warm:
            return
        self.manifest.add("pod", self.pod)
        pod_started = time.monotonic()
        _command(["podman", "pod", "create", "--name", self.pod, "--label", f"{OWNER}={self.sandbox.run_id}",
                  "--network=none", "--share=net,uts", "--userns=keep-id:uid=1000,gid=1000",
                  "--security-opt", f"label=level:{self.mcs}"])
        self.timings["pod_create_seconds"] = time.monotonic() - pod_started
        sidecars_started = time.monotonic()
        for name in self.case.services:
            self._service(name)
        self.timings["sidecars_ready_seconds"] = time.monotonic() - sidecars_started
        self.timings["setup_seconds"] = time.monotonic() - started

    def _base(self, name: str, *, network: bool = False, root_user: bool = False) -> list[str]:
        if self.sandbox.cancelled.is_set():
            raise SandboxError("trial cancelled")
        self.manifest.add("container", name)
        return ["podman", "run", "--pull=never", "--name", name, "--label", f"{OWNER}={self.sandbox.run_id}",
                "--http-proxy=false", "--security-opt=no-new-privileges", "--security-opt", f"label=level:{self.mcs}",
                "--cap-drop=all",
                *(["--cap-add=CHOWN", "--cap-add=DAC_OVERRIDE", "--cap-add=FOWNER",
                   "--cap-add=SETUID", "--cap-add=SETGID"] if root_user else []),
                "--pids-limit=1024", "--memory=24g" if network else "--memory=12g", "--cpus=8",
                *(["--network=pasta", "--userns=keep-id:uid=1000,gid=1000"] if network else ["--pod", self.pod]),
                "--user", "0:0" if root_user else "1000:1000"]

    def _mount(self, host: Path, target: str, readonly: bool = False) -> list[str]:
        # `:Z` relabels the host path for this trial's private MCS level; a path shared with
        # concurrent trials would be relabeled away from them, so only trial-owned paths mount.
        if not host.resolve().is_relative_to(self.root.resolve()):
            raise SandboxError(f"mount source outside the trial root: {host}")
        return ["--volume", f"{host}:{target}:{'ro,' if readonly else ''}Z"]

    def _env(self, *, warm: bool = False) -> dict[str, str]:
        values = {"HOME": HOME, "PATH": PATH, "PI_CONFIG_DIR": ".omp",
                  "PI_CODING_AGENT_DIR": HOME + "/.omp/agent", "XDG_CONFIG_HOME": HOME + "/.config",
                  "XDG_CACHE_HOME": HOME + "/.cache", "GIT_CONFIG_NOSYSTEM": "1",
                  "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
        for key, value in self.project.env.items():
            if key in values or key.startswith("GIT_CONFIG_"):
                raise SandboxError("project environment overrides sandbox-owned settings")
            if warm and (any(word in key.upper() for word in ("DATABASE", "TOKEN", "PASSWORD", "SECRET", "ACCESS_KEY")) or "://" in value):
                continue
            if "://" in value and urlsplit(value).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise SandboxError("project environment contains a non-fixture endpoint")
            values[key] = value
        return values

    def run_command(self, command: list[str], *, network: bool = False, warm: bool = False,
             extra_mounts: list[tuple[Path, str, bool]] | None = None,
             extra_env: dict[str, str] | None = None, stdout: IO[bytes] | int | None = subprocess.PIPE,
             check: bool = True, timeout: float = 3600, readonly: bool = False) -> subprocess.CompletedProcess[bytes]:
        name = self.name + "-exec-" + secrets.token_hex(4)
        argv = self._base(name, network=network)
        argv += ["--read-only", "--tmpfs", "/tmp:rw,size=2g", "--tmpfs", "/run:rw,size=64m",
                 *self._mount(self.repo, self.project.workdir, readonly),
                 *self._mount(self.home, HOME), *self._mount(self.control, "/control", True),
                 "--workdir", self.project.workdir]
        for cache in self.project.seed.cache_dirs:
            target = cache if cache.startswith("/") else self.project.workdir + "/" + cache
            argv += self._mount(self.cache_host(cache), target)
        for host, target, ro in extra_mounts or []:
            argv += self._mount(host, target, ro)
        env = self._env(warm=warm)
        env.update(extra_env or {})
        # env -i prevents image ENV credentials/proxies and host Podman defaults.
        command_env = [f"{key}={value}" for key, value in env.items()]
        argv += ["--entrypoint=/usr/bin/env", self.seed.image, "-i", *command_env, *command]
        return _command(argv, stdout=stdout, check=check, timeout=timeout)

    def _service(self, key: str) -> None:
        service = self.project.services[key]
        name = self.name + "-service-" + key
        env_path = self.control / ("service-" + key + ".env")
        _env_file(env_path, service.env)
        argv = self._base(name, root_user=True)
        argv += ["--detach", "--env-file", str(env_path)]
        if service.init:
            relative_path(service.init)
            init = self.root / "service-init" / key
            _copy(self.seed.root / "repo" / service.init, init)
            argv += self._mount(init, "/docker-entrypoint-initdb.d", True)
        _command([*argv, service.image, *service.args])
        wait_for_service(name, service.ready)

    def _relays(self, port: int) -> Path:
        started = time.monotonic()
        gateway, recorder = self.root / "gateway", self.root / "recorder"
        gateway.mkdir()
        recorder.mkdir()
        outside = self.name + "-host-relay"
        self.manifest.add("container", outside)
        _command(["podman", "run", "--pull=never", "--detach", "--name", outside, "--label", f"{OWNER}={self.sandbox.run_id}",
                  "--network=host", "--http-proxy=false", "--userns=keep-id:uid=1000,gid=1000", "--user=1000:1000",
                  "--security-opt", f"label=level:{self.mcs}", "--security-opt=no-new-privileges",
                  "--cap-drop=all", "--read-only", "--pids-limit=32", "--memory=64m", "--cpus=1",
                  *self._mount(gateway, "/gateway"), f"--entrypoint={SOCAT}", self.seed.image,
                  "UNIX-LISTEN:/gateway/model.sock,fork,mode=0600", f"TCP4:127.0.0.1:{port}"])
        self.timings["host_relay_seconds"] = time.monotonic() - started
        inner_started = time.monotonic()
        inner = self.name + "-inner-relay"
        _command([*self._base(inner), "--detach", "--read-only", *self._mount(gateway, "/gateway", True),
                  f"--entrypoint={SOCAT}", self.seed.image,
                  "TCP4-LISTEN:4000,bind=127.0.0.1,reuseaddr,fork", "UNIX-CONNECT:/gateway/model.sock"])
        self.timings["inner_relay_seconds"] = time.monotonic() - inner_started
        recorder_started = time.monotonic()
        (self.control / "recorder-server.py").write_text(_RECORDER_SERVER)
        _command([*self._base(self.recorder_name), "--detach", "--read-only",
                  *self._mount(recorder, "/recorder"), *self._mount(self.control, "/control", True),
                  f"--entrypoint={PYTHON}", self.seed.image, "/control/recorder-server.py"])
        self.timings["recorder_start_seconds"] = time.monotonic() - recorder_started
        return recorder

    def _trusted_diff(self, output: Path) -> None:
        script = '''set -eu
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_INDEX_FILE=/tmp/index
export GIT_OBJECT_DIRECTORY=/tmp/objects GIT_ALTERNATE_OBJECT_DIRECTORIES=/baseline/objects
mkdir -p /tmp/objects
cd /tree
git() { /usr/bin/git -c core.hooksPath=/dev/null -c core.fsmonitor=false -c core.autocrlf=false --git-dir=/baseline --work-tree=/tree "$@"; }
git read-tree HEAD
git add --all --force -- .
git diff --cached --binary --no-ext-diff --no-textconv HEAD -- .
'''
        name = self.name + "-diff"
        with output.open("wb") as stream:
            _command([*self._base(name), "--read-only", "--tmpfs", "/tmp:rw,size=2g",
                      *self._mount(self.repo, "/tree", True),
                      *self._mount(self.control / "baseline.git", "/baseline", True),
                      "--entrypoint=/bin/sh", self.seed.image, "-c", script], stdout=stream)

    def run_agent(self, port: int, token: str, model_roles: dict[str, str], output: Path,
                  readonly: bool = False) -> AgentRun:
        output.mkdir(parents=True, exist_ok=True)
        _json(output / "baseline-guidance.json",
              {path: base64.b64encode(data).decode("ascii") for path, data in self.baseline_guidance.items()})
        if not 1 <= port <= 65535:
            raise ValueError("invalid dispatcher port")
        (self.control / "omp.yml").write_text(render_settings(model_roles))
        agent_config = self.home / ".omp/agent"
        agent_config.mkdir(parents=True, exist_ok=True)
        providers = {model.split("/", 1)[0]: {"transport": "pi-native", "baseUrl": "http://127.0.0.1:4000", "apiKey": token}
                     for model in model_roles.values()}
        _json(agent_config / "models.yml", {"providers": providers})
        recorder = self._relays(port)
        wrappers = self.root / "recorders"
        wrappers.mkdir()
        for name in ("git", "gh", "ssh", "scp", "sftp", "docker", "podman", "kubectl", "psql", "pg_dump", "pg_restore",
                     "mysql", "redis-cli", "aws", "mc", "gcloud", "terraform", "curl", "wget"):
            path = wrappers / name
            path.write_text(_RECORDER_WRAPPER)
            path.chmod(0o755)
        (wrappers / ".services").write_text("".join(name + "\n" for name in self.case.services))
        # In-pod preflight waits on actual socket availability, not a guessed delay.
        fixture_5432 = any(
            "5432" in " ".join([service.ready, *service.args])
            or ("postgres" in service.image and "-p" not in service.args)
            for key, service in self.project.services.items() if key in self.case.services)
        probe = '''import json, os, socket, threading, time
RELAY_READY_POLL_SECONDS = 0.05
deadline = time.monotonic() + 15
stop = threading.Event()
while not all(os.path.exists(p) for p in ['/gateway/model.sock', '/recorder/ready']):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError('relay socket missing')
    stop.wait(min(RELAY_READY_POLL_SECONDS, remaining))
result = {'network': 'none', 'host_home_absent': not os.path.exists(HOST_HOME), 'ssh_absent': not os.path.exists('/root/.ssh'),
          'sandbox_ssh_absent': not os.path.exists('/home/eval/.ssh'),
          'host_credential_store_absent': not os.path.exists('/home/eval/.omp/agent/agent.db')}
s = socket.socket(); s.settimeout(2)
result['external_connect_denied'] = s.connect_ex(('1.1.1.1', 443)) != 0
s.close()
if EXPECT_5432_DENIED:
    s = socket.socket(); s.settimeout(2)
    result['loopback_5432_denied'] = s.connect_ex(('127.0.0.1', 5432)) != 0
    s.close()
if not all(v for k, v in result.items() if k != 'network'):
    raise RuntimeError('sandbox isolation preflight failed')
print(json.dumps(result))
'''
        probe = probe.replace("EXPECT_5432_DENIED", repr(not fixture_5432))
        probe = probe.replace("HOST_HOME", repr(str(Path.home())))
        mounts = [(recorder, "/recorder", True), (wrappers, "/recorders", True), (self.root / "gateway", "/gateway", True)]
        preflight_started = time.monotonic()
        result = self.run_command([PYTHON, "-c", probe], extra_mounts=mounts)
        (output / "isolation.json").write_bytes(result.stdout)
        self.timings["preflight_seconds"] = time.monotonic() - preflight_started
        started = time.monotonic()
        started_at = time.time()
        with (output / "events.jsonl").open("wb") as events:
            try:
                result = self.run_command(["omp", "--profile", "default", "--cwd", self.project.workdir,
                                    "--config", "/control/omp.yml", "--no-extensions", "--no-title", "--mode", "json",
                                    "-p", "--wait-async", "--max-time", self.case.budget.max_time,
                                    "--max-cost", str(self.case.budget.max_cost), "--session-dir", HOME + "/transcripts",
                                    "--model", model_roles["default"],
                                    *(["--tools", "read,grep,glob,find"] if readonly else []),
                                    self.case.prompt],
                                   extra_mounts=mounts, stdout=events, check=False, readonly=readonly,
                                   timeout=_duration(self.case.budget.max_time) + 30)
            except subprocess.TimeoutExpired:
                # Kill the named container before touching agent-writable artifacts.
                for resource in self.manifest.resources:
                    if resource["name"].startswith(self.name + "-exec-") and _owned("container", resource["name"], self.sandbox.run_id):
                        _command(["podman", "kill", resource["name"]], check=False)
                result = subprocess.CompletedProcess([], 124, b"", b"")
        elapsed = time.monotonic() - started
        (output / "agent.stderr").write_bytes(result.stderr or b"")
        self.timings["agent_seconds"] = elapsed
        diff_started = time.monotonic()
        # All agent processes are gone; trusted capture ignores its mutable git index.
        self._trusted_diff(output / "diff.patch")
        self.timings["diff_seconds"] = time.monotonic() - diff_started
        sessions_started = time.monotonic()
        sessions = self.home / "transcripts"
        destination = output / "sessions"
        destination.mkdir(exist_ok=True)
        if sessions.is_dir() and not sessions.is_symlink():
            for session in sessions.rglob("*"):
                if session.is_symlink():
                    raise SandboxError("session output contains a symlink")
                if session.is_file():
                    target = destination / session.relative_to(sessions)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(session, target)
        self.timings["sessions_seconds"] = time.monotonic() - sessions_started
        recorder_started = time.monotonic()
        logs = _command(["podman", "logs", self.recorder_name])
        (output / "recorder.jsonl").write_bytes(logs.stdout)
        _json(output / "recorder-summary.json", parse_recorder_log(logs.stdout.decode()))
        running = _command(["podman", "inspect", "--format", "{{.State.Running}}", self.recorder_name])
        if running.stdout.strip() != b"true":
            raise SandboxError("command recorder terminated unexpectedly")
        self.timings["recorder_collection_seconds"] = time.monotonic() - recorder_started
        return {"seconds": elapsed, "phases": self.timings, "started_at": started_at}

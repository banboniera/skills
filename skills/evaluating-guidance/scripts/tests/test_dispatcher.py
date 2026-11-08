"""The pure Bun ledger suite never imports the credential-owning SDK."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def test_token_budget_and_usage_boundaries() -> None:
    bun = shutil.which("bun")
    assert bun is not None, "The dispatcher requires an installed Bun runtime"
    scripts = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [bun, "test", str(scripts / "dispatcher")],
        cwd=scripts, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_janitor_reaps_only_unlocked_owned_dispatcher(tmp_path: Path) -> None:
    import fcntl
    import sys
    from guidance_evals.dispatcher import reap_dispatchers
    root = tmp_path / "runs/one/dispatcher"
    root.mkdir(parents=True)
    script = Path(__file__).resolve().parents[1] / "dispatcher/host.ts"
    child = subprocess.Popen([sys.executable, "-c", "import signal; signal.pause()", str(script)], cwd=root)
    try:
        (root / "dispatcher.pid").write_text(str(child.pid))
        (root / "dispatcher.ready.json").write_text("{}")
        with (root / "dispatcher.lock").open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            assert reap_dispatchers(tmp_path)["dispatchers_active"] == 1
            assert child.poll() is None
        assert reap_dispatchers(tmp_path)["dispatchers_cleaned"] == 1
        child.wait(timeout=5)
        assert not (root / "dispatcher.pid").exists()
        assert not (root / "dispatcher.ready.json").exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()

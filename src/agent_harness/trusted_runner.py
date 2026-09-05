from __future__ import annotations
import hashlib, os, shutil, subprocess, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

class TrustedRunnerError(RuntimeError): pass
class ActionNotAllowedError(TrustedRunnerError): pass

def _utc_now() -> str: return datetime.now(timezone.utc).isoformat()
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

@dataclass(frozen=True, slots=True)
class RunnerResult:
    action: str
    cwd: Path
    exit_code: int | None
    timed_out: bool
    stdout_path: Path
    stderr_path: Path
    stdout_hash: str
    stderr_hash: str
    started_at: str
    ended_at: str

class TrustedRunner:
    def __init__(self, *, evidence_root: str | Path, trusted_hooks_path: str | Path | None = None, extra_actions: dict[str, tuple[str, ...]] | None = None) -> None:
        self.evidence_root = Path(evidence_root).resolve(); self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.home = self.evidence_root / "runner-home"; self.home.mkdir(parents=True, exist_ok=True)
        self.trusted_hooks_path = Path(trusted_hooks_path).resolve() if trusted_hooks_path is not None else self.evidence_root / "trusted-git-hooks"
        self.trusted_hooks_path.mkdir(parents=True, exist_ok=True)
        git = shutil.which("git")
        if git is None: raise TrustedRunnerError("git executable not found")
        self._actions = {"git_status": (git,"status","--short"), "git_diff": (git,"diff","--stat"), "git_rev_parse": (git,"rev-parse","HEAD"), "pytest": (sys.executable,"-m","pytest","-q")}
        if extra_actions:
            for name, command in extra_actions.items():
                if name in self._actions: raise ValueError(f"cannot override trusted action: {name}")
                if not command: raise ValueError(f"action command must not be empty: {name}")
                self._actions[name] = tuple(command)

    def run(self, action: str, *, cwd: str | Path, timeout_s: float) -> RunnerResult:
        if action not in self._actions: raise ActionNotAllowedError(action)
        if timeout_s <= 0: raise ValueError("timeout_s must be > 0")
        run_dir = self.evidence_root / f"action-{uuid4()}"; run_dir.mkdir(parents=True, exist_ok=False)
        stdout_path = run_dir / "stdout.log"; stderr_path = run_dir / "stderr.log"; started_at = _utc_now()
        try:
            completed = subprocess.run(self._actions[action], cwd=Path(cwd).resolve(), env=self._build_env(), text=True, capture_output=True, timeout=timeout_s, check=False, shell=False)
            stdout, stderr, exit_code, timed_out = completed.stdout or "", completed.stderr or "", completed.returncode, False
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, exit_code, timed_out = self._coerce_text(exc.stdout), self._coerce_text(exc.stderr), None, True
        stdout_path.write_text(stdout, encoding="utf-8"); stderr_path.write_text(stderr, encoding="utf-8")
        return RunnerResult(action, Path(cwd).resolve(), exit_code, timed_out, stdout_path, stderr_path, _sha256_file(stdout_path), _sha256_file(stderr_path), started_at, _utc_now())

    def _build_env(self) -> dict[str, str]:
        env = {"HOME": str(self.home), "CI": os.environ.get("CI", "1"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(self.trusted_hooks_path)}
        for key in ("PATH","LANG","LC_ALL"):
            value = os.environ.get(key)
            if value is not None: env[key] = value
        return env

    @staticmethod
    def _coerce_text(value):
        if value is None: return ""
        if isinstance(value, bytes): return value.decode("utf-8", errors="replace")
        return value

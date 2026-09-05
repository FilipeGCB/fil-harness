from __future__ import annotations
import re
import subprocess
from pathlib import Path


class GitWorkspaceError(RuntimeError):
    pass


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not cleaned:
        raise ValueError("identifier must contain a safe path component")
    return cleaned


class GitWorkspaceManager:
    def __init__(self, *, repo_path: str | Path, runtime_root: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        self.writer_root = self.runtime_root / "worktrees"
        self.verify_root = self.runtime_root / "verify"
        self.trusted_hooks = self.runtime_root / "trusted-git-hooks"
        self.writer_root.mkdir(parents=True, exist_ok=True)
        self.verify_root.mkdir(parents=True, exist_ok=True)
        self.trusted_hooks.mkdir(parents=True, exist_ok=True)

    def create_writer_worktree(self, *, task_id: str, base_sha: str) -> Path:
        safe_id = _safe_component(task_id)
        path = self.writer_root / safe_id
        branch = f"harness/{safe_id}"
        self._ensure_absent(path)
        self._git("worktree", "add", "-b", branch, str(path), base_sha)
        return path

    def candidate_head(self, writer_path: str | Path) -> str:
        writer = Path(writer_path).resolve()
        result = self._run(["git", "-C", str(writer), "rev-parse", "HEAD"])
        return result.stdout.strip()

    def create_verification_checkout(self, *, head_sha: str, run_id: str) -> Path:
        safe_id = _safe_component(run_id)
        path = self.verify_root / safe_id
        self._ensure_absent(path)
        self._git("-c", f"core.hooksPath={self.trusted_hooks}", "worktree", "add", "--detach", str(path), head_sha)
        return path

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run(["git", "-C", str(self.repo_path), *args])

    @staticmethod
    def _ensure_absent(path: Path) -> None:
        if path.exists():
            raise GitWorkspaceError(f"worktree path already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise GitWorkspaceError(f"git command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.strip()}")
        return completed

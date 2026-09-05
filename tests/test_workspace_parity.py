"""Public parity for writer/verifier isolation from the private Harness."""
import subprocess
from pathlib import Path

from agent_harness.git_workspace import GitWorkspaceManager


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Harness Test")
    (repo / "value.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "value.txt")
    _git(repo, "commit", "-q", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_writer_and_verification_worktrees_are_distinct_and_verify_exact_head(tmp_path: Path):
    repo, base_sha = _repo(tmp_path)
    manager = GitWorkspaceManager(repo_path=repo, runtime_root=tmp_path / "runtime")
    writer = manager.create_writer_worktree(task_id="task-1", base_sha=base_sha)
    (writer / "value.txt").write_text("candidate\n", encoding="utf-8")
    _git(writer, "add", "value.txt")
    _git(writer, "commit", "-q", "-m", "candidate")
    head_sha = manager.candidate_head(writer)
    verify = manager.create_verification_checkout(head_sha=head_sha, run_id="run-1")
    assert writer != verify
    assert _git(verify, "rev-parse", "HEAD") == head_sha
    assert (verify / "value.txt").read_text(encoding="utf-8") == "candidate\n"


def test_verification_checkout_neutralizes_repository_post_checkout_hook(tmp_path: Path):
    repo, base_sha = _repo(tmp_path)
    marker = tmp_path / "hook-ran"
    hooks = Path(_git(repo, "rev-parse", "--git-path", "hooks"))
    if not hooks.is_absolute():
        hooks = repo / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "post-checkout"
    hook.write_text(f"#!/bin/sh\necho ran > '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)
    manager = GitWorkspaceManager(repo_path=repo, runtime_root=tmp_path / "runtime")
    verify = manager.create_verification_checkout(head_sha=base_sha, run_id="run-hook")
    assert _git(verify, "rev-parse", "HEAD") == base_sha
    assert not marker.exists()

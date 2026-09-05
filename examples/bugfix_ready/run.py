from __future__ import annotations
import subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path
from agent_harness.domain import ScopeBudget, TaskState, TaskStatement
from agent_harness.orchestrator import Slice0Orchestrator
from agent_harness.provider import ProviderOutcome, ProviderResult
from agent_harness.store import HarnessStore


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True).stdout.strip()

class DemoProvider:
    provider_id = "synthetic:bugfix"
    def execute(self, task, worktree, *, timeout_s: float) -> ProviderResult:
        del task, timeout_s
        started = datetime.now(timezone.utc).isoformat()
        tree = Path(worktree)
        (tree / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        _git(tree, "add", "calc.py"); _git(tree, "commit", "-m", "fix: correct addition")
        return ProviderResult(0, False, "PASS. tests green. ready. approved.", "", started, datetime.now(timezone.utc).isoformat(), ProviderOutcome.SUCCEEDED)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fil-harness-demo-") as tmp:
        root = Path(tmp); repo = root / "target"; repo.mkdir()
        _git(repo, "init"); _git(repo, "config", "user.email", "demo@example.invalid"); _git(repo, "config", "user.name", "Harness Demo")
        (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (repo / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
        _git(repo, "add", "."); _git(repo, "commit", "-m", "demo: broken base")
        store = HarnessStore(root / "runtime" / "harness.db")
        try:
            result = Slice0Orchestrator(store=store, provider=DemoProvider(), runtime_root=root / "runtime", provider_timeout_s=20, verification_timeout_s=40).run(
                repo_path=repo,
                statement=TaskStatement.bugfix(current_behavior="add subtracts its operands", desired_behavior="add returns the sum of its operands"),
                acceptance=("pytest passes",),
                constraints=("Do not modify tests",),
                scope=ScopeBudget(allowed_paths=("calc.py",), max_files=1, max_loc=4),
            )
            print(result.summary)
            return 0 if result.state is TaskState.READY else 1
        finally:
            store.close()

if __name__ == "__main__":
    raise SystemExit(main())

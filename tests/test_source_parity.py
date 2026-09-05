"""Neutralized parity checks carried from the private Harness core test suite."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from agent_harness.canonical import canonical_json, sha256_canonical
from agent_harness.domain import ScopeBudget, TaskIntake, TaskState, TaskStatement, transition_allowed
from agent_harness.orchestrator import Slice0Orchestrator
from agent_harness.policy import PolicyDecision, Slice0Policy
from agent_harness.provider import FixedCommandProvider, ProviderAttempt, ProviderOutcome, ProviderResult
from agent_harness.retry_policy import may_auto_retry, retry_denial_reason
from agent_harness.scope import evaluate_scope
from agent_harness.store import HarnessStore, IllegalTransitionError
from agent_harness.trusted_runner import ActionNotAllowedError, TrustedRunner
from agent_harness.verification import VerificationSurfaceStatus, inspect_verification_surface

ADD_BUGFIX = TaskStatement.bugfix(
    current_behavior="add() returns the difference of its arguments",
    desired_behavior="add() returns the sum of its arguments",
)


def _intake(scope: ScopeBudget | None = None) -> TaskIntake:
    return TaskIntake.create(
        statement=ADD_BUGFIX,
        acceptance=("pytest passes",),
        constraints=("do not merge",),
        scope=scope or ScopeBudget(),
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True).stdout.strip()


def _buggy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Harness Test")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "buggy base")
    return repo


# canonical.py + domain.py parity

def test_canonical_json_ignores_mapping_insertion_order():
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_hash_is_stable_for_equivalent_payloads():
    assert sha256_canonical({"b": 2, "a": 1}) == sha256_canonical({"a": 1, "b": 2})


def test_task_intake_precomputes_stable_hashes_and_is_frozen():
    intake = _intake(ScopeBudget(allowed_paths=("src/**",), max_files=3, max_loc=50))
    assert all(len(value) == 64 for value in (intake.goal_hash, intake.acceptance_hash, intake.constraints_hash, intake.scope_budget_hash))
    with pytest.raises(FrozenInstanceError):
        intake.acceptance_hash = "changed"


def test_all_frozen_legal_edges_are_allowed():
    legal = {
        TaskState.PENDING: {TaskState.RUNNING, TaskState.BLOCKED},
        TaskState.RUNNING: {TaskState.VERIFYING, TaskState.INTERRUPTED, TaskState.BLOCKED, TaskState.FAILED},
        TaskState.VERIFYING: {TaskState.READY, TaskState.RUNNING, TaskState.BLOCKED, TaskState.FAILED},
        TaskState.READY: {TaskState.WAITING_HUMAN, TaskState.DONE},
        TaskState.WAITING_HUMAN: {TaskState.RUNNING, TaskState.DONE, TaskState.BLOCKED},
        TaskState.INTERRUPTED: {TaskState.RUNNING, TaskState.BLOCKED, TaskState.FAILED},
        TaskState.BLOCKED: {TaskState.RUNNING, TaskState.WAITING_HUMAN, TaskState.FAILED},
        TaskState.FAILED: set(),
        TaskState.DONE: set(),
    }
    for current in TaskState:
        for target in TaskState:
            assert transition_allowed(current, target) is (target in legal[current])


# policy.py parity

@pytest.mark.parametrize(
    ("capability", "expected"),
    [
        ("edit_task_worktree", PolicyDecision.ALLOW),
        ("merge", PolicyDecision.HUMAN),
        ("force_push", PolicyDecision.DENY),
        ("invented_capability", PolicyDecision.DENY),
    ],
)
def test_policy_decisions_match_private_core(capability, expected):
    assert Slice0Policy().decide(capability) is expected


# provider.py + prompt parity

def test_provider_timeout_is_typed_and_bounded(tmp_path: Path):
    provider = FixedCommandProvider((sys.executable, "-c", "import time; time.sleep(2)"))
    result = provider.execute(_intake(), tmp_path, timeout_s=0.05)
    assert result.timed_out
    assert result.exit_code is None
    assert result.outcome is ProviderOutcome.TIMED_OUT


def test_provider_identity_does_not_leak_arguments():
    provider = FixedCommandProvider((sys.executable, "-c", "pass", "--token", "synthetic-secret-value"))
    assert "synthetic-secret-value" not in provider.provider_id
    assert "--token" not in provider.provider_id


def test_provider_prompt_carries_scope_but_not_control_hashes():
    scope = ScopeBudget(allowed_paths=("src/agent_harness/gates.py", "src/agent_harness/scope.py"), max_files=2, max_loc=40)
    intake = _intake(scope)
    payload = FixedCommandProvider(("true",))._prompt(intake)
    assert "src/agent_harness/gates.py" in payload
    assert "max_files: 2" in payload
    assert "max_loc: 40" in payload
    assert intake.scope_budget_hash not in payload
    assert intake.acceptance_hash not in payload
    assert intake.goal_hash not in payload


def test_provider_outcome_vocabulary_is_complete():
    assert {item.value for item in ProviderOutcome} == {
        "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "QUOTA_EXHAUSTED",
        "AUTH_UNAVAILABLE", "TRANSPORT_FAILED", "OUTCOME_UNKNOWN",
    }


def test_unclassified_provider_result_defaults_to_unknown():
    result = ProviderResult(0, False, "", "", "start", "end")
    assert result.outcome is ProviderOutcome.OUTCOME_UNKNOWN


def test_attempt_captures_durable_identity_and_candidate():
    result = ProviderResult(0, False, "", "", "start", "end", ProviderOutcome.SUCCEEDED)
    first = ProviderAttempt.from_result(task_id="task", run_id="run", provider_id="provider", attempt_number=1, result=result, candidate_sha="abc")
    second = ProviderAttempt.from_result(task_id="task", run_id="run", provider_id="provider", attempt_number=1, result=result, candidate_sha="abc")
    assert first.attempt_id != second.attempt_id
    assert first.candidate_sha == "abc"
    assert first.outcome is ProviderOutcome.SUCCEEDED


# scope.py parity

def test_scope_allows_paths_inside_budget():
    report = evaluate_scope(changed_paths=("src/core.py", "tests/test_core.py"), changed_loc=42, budget=ScopeBudget(allowed_paths=("src/**", "tests/**"), max_files=3, max_loc=100))
    assert report.ok and report.violations == ()


def test_scope_rejects_path_file_count_loc_and_unmeasurable_changes():
    report = evaluate_scope(changed_paths=("a.py", "b.py", "prod/deploy.sh"), changed_loc=51, budget=ScopeBudget(allowed_paths=("*.py",), max_files=2, max_loc=50), unmeasurable_paths=("asset.bin",))
    assert not report.ok
    assert "path_not_allowed:prod/deploy.sh" in report.violations
    assert "max_files_exceeded:3>2" in report.violations
    assert "max_loc_exceeded:51>50" in report.violations
    assert "loc_unmeasurable:asset.bin" in report.violations


# store.py parity

def test_store_enables_required_sqlite_pragmas(tmp_path: Path):
    store = HarnessStore(tmp_path / "harness.db")
    assert store.pragma("journal_mode").lower() == "wal"
    assert int(store.pragma("foreign_keys")) == 1
    assert int(store.pragma("busy_timeout")) > 0


def test_illegal_transition_preserves_state_and_event_count(tmp_path: Path):
    store = HarnessStore(tmp_path / "harness.db")
    task_id = store.create_task(intake=_intake(), base_sha="abc123")
    before = store.event_count(task_id)
    with pytest.raises(IllegalTransitionError):
        store.transition_task(task_id, TaskState.READY)
    assert store.get_task(task_id).state is TaskState.PENDING
    assert store.event_count(task_id) == before


def test_store_persists_head_and_evidence(tmp_path: Path):
    store = HarnessStore(tmp_path / "harness.db")
    task_id = store.create_task(intake=_intake(), base_sha="base")
    store.transition_task(task_id, TaskState.RUNNING)
    store.set_head_sha(task_id, "head")
    run_id = store.create_run(task_id)
    evidence_id = store.record_evidence(task_id=task_id, run_id=run_id, metadata={"head_sha": "head", "exit_code": 0})
    assert store.get_task(task_id).head_sha == "head"
    assert store.get_evidence_metadata(evidence_id) == {"exit_code": 0, "head_sha": "head"}


# trusted_runner.py parity

def test_trusted_runner_rejects_arbitrary_action(tmp_path: Path):
    runner = TrustedRunner(evidence_root=tmp_path / "evidence")
    with pytest.raises(ActionNotAllowedError):
        runner.run("rm_everything", cwd=tmp_path, timeout_s=1)


def test_trusted_runner_does_not_inherit_parent_secret(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HARNESS_FAKE_SECRET", "synthetic-secret")
    runner = TrustedRunner(evidence_root=tmp_path / "evidence", extra_actions={"env_probe": (sys.executable, "-c", "import os; print(os.environ.get('HARNESS_FAKE_SECRET', 'MISSING'))")})
    result = runner.run("env_probe", cwd=tmp_path, timeout_s=2)
    assert result.stdout_path.read_text(encoding="utf-8").strip() == "MISSING"


def test_trusted_runner_timeout_is_recorded_with_hashes(tmp_path: Path):
    runner = TrustedRunner(evidence_root=tmp_path / "evidence", extra_actions={"sleep_probe": (sys.executable, "-c", "import time; time.sleep(2)")})
    result = runner.run("sleep_probe", cwd=tmp_path, timeout_s=0.05)
    assert result.timed_out and result.exit_code is None
    assert len(result.stdout_hash) == 64 and len(result.stderr_hash) == 64


# verification.py parity

def _verification_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init"); _git(repo, "config", "user.email", "test@example.invalid"); _git(repo, "config", "user.name", "Harness Test")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests").mkdir(); (repo / "tests" / "test_app.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "."); _git(repo, "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_test_change_requires_justification(tmp_path: Path):
    repo, base = _verification_repo(tmp_path)
    (repo / "tests" / "test_app.py").write_text("def test_value():\n    assert 1 == 1\n", encoding="utf-8")
    _git(repo, "add", "."); _git(repo, "commit", "-m", "change test")
    report = inspect_verification_surface(repo_path=repo, base_sha=base, head_sha=_git(repo, "rev-parse", "HEAD"))
    assert report.status is VerificationSurfaceStatus.REQUIRES_JUSTIFICATION
    assert report.sensitive_paths == ("tests/test_app.py",)


def test_normal_source_change_is_clean(tmp_path: Path):
    repo, base = _verification_repo(tmp_path)
    (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "."); _git(repo, "commit", "-m", "fix app")
    report = inspect_verification_surface(repo_path=repo, base_sha=base, head_sha=_git(repo, "rev-parse", "HEAD"))
    assert report.status is VerificationSurfaceStatus.CLEAN
    assert report.sensitive_paths == ()


# retry_policy.py parity

@pytest.mark.parametrize("outcome", [ProviderOutcome.OUTCOME_UNKNOWN, ProviderOutcome.CANCELLED, ProviderOutcome.QUOTA_EXHAUSTED, ProviderOutcome.AUTH_UNAVAILABLE, ProviderOutcome.TRANSPORT_FAILED, ProviderOutcome.TIMED_OUT])
def test_nonretryable_outcomes_stay_nonretryable(outcome):
    assert may_auto_retry(outcome) is False
    assert retry_denial_reason(outcome) == f"retry_denied:{outcome.value}"


@pytest.mark.parametrize("outcome", [ProviderOutcome.SUCCEEDED, ProviderOutcome.FAILED])
def test_classified_terminal_outcomes_may_retry(outcome):
    assert may_auto_retry(outcome) is True
    assert retry_denial_reason(outcome) is None


class CountingProvider:
    provider_id = "in-process:counting"
    def __init__(self, outcome: ProviderOutcome) -> None:
        self.outcome = outcome
        self.calls = 0
    def execute(self, task, worktree, *, timeout_s: float) -> ProviderResult:
        del task, timeout_s
        self.calls += 1
        started = datetime.now(timezone.utc).isoformat()
        tree = Path(worktree)
        (tree / "calc.py").write_text(f"def add(a, b):\n    return a * b + {self.calls}\n", encoding="utf-8")
        _git(tree, "add", "calc.py"); _git(tree, "commit", "-m", f"wrong candidate {self.calls}")
        return ProviderResult(0, False, "PASS", "", started, datetime.now(timezone.utc).isoformat(), self.outcome)


def test_orchestrator_refuses_to_retry_unknown_outcome(tmp_path: Path):
    repo = _buggy_repo(tmp_path)
    provider = CountingProvider(ProviderOutcome.OUTCOME_UNKNOWN)
    store = HarnessStore(tmp_path / "runtime" / "harness.db")
    result = Slice0Orchestrator(store=store, provider=provider, runtime_root=tmp_path / "runtime", provider_timeout_s=10, verification_timeout_s=30, max_attempts=3).run(
        repo_path=repo, statement=ADD_BUGFIX, acceptance=("pytest passes",), constraints=(), scope=ScopeBudget(allowed_paths=("calc.py",), max_files=1, max_loc=8)
    )
    assert provider.calls == 1
    assert result.state is TaskState.BLOCKED
    assert "retry_denied:OUTCOME_UNKNOWN" in result.failures


def test_orchestrator_retries_clean_success_rejected_by_gates(tmp_path: Path):
    repo = _buggy_repo(tmp_path)
    provider = CountingProvider(ProviderOutcome.SUCCEEDED)
    store = HarnessStore(tmp_path / "runtime" / "harness.db")
    result = Slice0Orchestrator(store=store, provider=provider, runtime_root=tmp_path / "runtime", provider_timeout_s=10, verification_timeout_s=30, max_attempts=2).run(
        repo_path=repo, statement=ADD_BUGFIX, acceptance=("pytest passes",), constraints=(), scope=ScopeBudget(allowed_paths=("calc.py",), max_files=1, max_loc=8)
    )
    assert provider.calls == 2
    assert result.state is TaskState.BLOCKED
    assert "retry_budget_exhausted" in result.failures

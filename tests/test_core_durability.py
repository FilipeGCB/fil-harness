from agent_harness.domain import ScopeBudget, TaskIntake, TaskState, TaskStatement
from agent_harness.scope import evaluate_scope
from agent_harness.store import HarnessStore
from agent_harness.trusted_runner import ActionNotAllowedError, TrustedRunner


def _intake():
    return TaskIntake.create(
        statement=TaskStatement.feature(desired_behavior="add a public behavior"),
        acceptance=("tests pass",),
        constraints=("keep scope bounded",),
        scope=ScopeBudget(allowed_paths=("src/*.py",), max_files=2, max_loc=20),
    )


def test_sqlite_reconstructs_typed_intake_after_restart(tmp_path):
    path = tmp_path / "harness.db"
    store = HarnessStore(path)
    task_id = store.create_task(intake=_intake(), base_sha="a" * 40)
    store.transition_task(task_id, TaskState.RUNNING)
    hashes_before = (
        store.get_task(task_id).goal_hash,
        store.get_task(task_id).acceptance_hash,
        store.get_task(task_id).constraints_hash,
        store.get_task(task_id).scope_budget_hash,
    )
    store.close()

    reopened = HarnessStore(path)
    rebuilt = reopened.get_task_intake(task_id)
    assert reopened.get_task(task_id).state is TaskState.RUNNING
    assert (rebuilt.goal_hash, rebuilt.acceptance_hash, rebuilt.constraints_hash, rebuilt.scope_budget_hash) == hashes_before


def test_scope_budget_rejects_path_and_loc_overrun():
    report = evaluate_scope(
        changed_paths=("src/a.py", "tests/test_a.py"),
        changed_loc=25,
        budget=ScopeBudget(allowed_paths=("src/*.py",), max_files=2, max_loc=20),
    )
    assert not report.ok
    assert "path_not_allowed:tests/test_a.py" in report.violations
    assert "max_loc_exceeded:25>20" in report.violations


def test_trusted_runner_rejects_unallowlisted_action(tmp_path):
    runner = TrustedRunner(evidence_root=tmp_path / "evidence")
    try:
        runner.run("provider_defined_action", cwd=tmp_path, timeout_s=1)
    except ActionNotAllowedError:
        pass
    else:
        raise AssertionError("unallowlisted action was accepted")

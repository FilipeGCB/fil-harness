"""Public parity for the typed intake semantics proven in the private Harness."""
import pytest

from agent_harness.context import context_hash, provider_context
from agent_harness.domain import ScopeBudget, TaskIntake, TaskIntent, TaskStatement
from agent_harness.provider import FixedCommandProvider
from agent_harness.store import HarnessStore

AMBIGUOUS = (
    "median() returns the upper middle element for even-length input instead "
    "of the average of the two middle values"
)


def _bugfix() -> TaskStatement:
    return TaskStatement.bugfix(
        current_behavior=AMBIGUOUS,
        desired_behavior="median() returns the average of the two middle values for even-length input",
    )


def _intake(statement: TaskStatement) -> TaskIntake:
    return TaskIntake.create(
        statement=statement,
        acceptance=("pytest passes",),
        constraints=("Do not modify tests",),
        scope=ScopeBudget(allowed_paths=("stats.py",), max_files=1, max_loc=12),
    )


def test_bugfix_separates_defect_from_requirement():
    statement = _bugfix()
    assert statement.intent is TaskIntent.BUGFIX
    assert statement.current_behavior == AMBIGUOUS
    assert statement.desired_behavior.startswith("median() returns the average")


def test_bugfix_without_current_behavior_is_refused():
    with pytest.raises(ValueError, match="current_behavior"):
        TaskStatement.bugfix(current_behavior="", desired_behavior="median() averages")


def test_bugfix_with_identical_current_and_desired_behavior_is_refused():
    with pytest.raises(ValueError, match="differ"):
        TaskStatement.bugfix(current_behavior=AMBIGUOUS, desired_behavior=AMBIGUOUS)


def test_statement_requires_desired_behavior():
    with pytest.raises(ValueError, match="desired_behavior"):
        TaskStatement.feature(desired_behavior="   ")


def test_feature_does_not_require_current_behavior():
    statement = TaskStatement.feature(desired_behavior="median() accepts an empty sequence")
    assert statement.intent is TaskIntent.FEATURE
    assert statement.current_behavior is None


def test_refactor_may_describe_current_structure():
    statement = TaskStatement.refactor(
        current_behavior="median() branches on parity inline",
        desired_behavior="median() delegates parity handling to a helper",
    )
    assert statement.intent is TaskIntent.REFACTOR
    assert statement.current_behavior == "median() branches on parity inline"


def test_untyped_intake_is_not_constructible():
    with pytest.raises(TypeError):
        TaskIntake.create(  # type: ignore[call-arg]
            goal=AMBIGUOUS,
            acceptance=(),
            constraints=(),
            scope=ScopeBudget(),
        )


def test_provider_context_labels_fact_and_requirement():
    context = provider_context(_intake(_bugfix()))
    assert context["intent"] == "BUGFIX"
    assert context["current_behavior"] == AMBIGUOUS
    assert context["desired_behavior"].startswith("median() returns the average")


def test_provider_context_has_no_unlabelled_goal():
    assert "goal" not in provider_context(_intake(_bugfix()))


def test_provider_context_hash_is_deterministic():
    assert context_hash(_intake(_bugfix())) == context_hash(_intake(_bugfix()))


def test_swapping_defect_and_requirement_changes_task_identity():
    forwards = _intake(_bugfix())
    backwards = _intake(
        TaskStatement.bugfix(
            current_behavior=_bugfix().desired_behavior,
            desired_behavior=AMBIGUOUS,
        )
    )
    assert context_hash(forwards) != context_hash(backwards)


def test_intent_alone_changes_task_identity():
    as_bugfix = _intake(TaskStatement.bugfix(current_behavior="a", desired_behavior="b"))
    as_refactor = _intake(TaskStatement.refactor(current_behavior="a", desired_behavior="b"))
    assert context_hash(as_bugfix) != context_hash(as_refactor)
    assert as_bugfix.goal_hash != as_refactor.goal_hash


def test_bugfix_payload_marks_current_behavior_as_not_the_specification():
    payload = FixedCommandProvider(("true",))._prompt(_intake(_bugfix()))
    assert AMBIGUOUS in payload
    assert "do not implement" in payload.lower()
    assert "Current behaviour" in payload
    assert "Required behaviour" in payload


def test_refactor_payload_preserves_observable_behavior():
    payload = FixedCommandProvider(("true",))._prompt(
        _intake(TaskStatement.refactor(desired_behavior="median() delegates to a helper"))
    )
    assert "observable behaviour must not change" in payload.lower()


def test_feature_payload_does_not_invent_current_behavior():
    payload = FixedCommandProvider(("true",))._prompt(
        _intake(TaskStatement.feature(desired_behavior="median() accepts an empty sequence"))
    )
    assert "Current behaviour" not in payload


def test_provider_payload_leaks_no_control_hashes():
    intake = _intake(_bugfix())
    payload = FixedCommandProvider(("true",))._prompt(intake)
    for owned in (
        intake.goal_hash,
        intake.acceptance_hash,
        intake.constraints_hash,
        intake.scope_budget_hash,
    ):
        assert owned not in payload


def test_typed_statement_survives_restart(tmp_path):
    db = tmp_path / "runtime" / "harness.db"
    intake = _intake(_bugfix())
    store = HarnessStore(db)
    task_id = store.create_task(intake=intake, base_sha="base")
    store.close()
    reopened = HarnessStore(db)
    recovered = reopened.get_task_intake(task_id)
    assert recovered.statement == intake.statement
    assert recovered.statement.intent is TaskIntent.BUGFIX
    assert context_hash(recovered) == context_hash(intake)
    assert recovered.goal_hash == intake.goal_hash


def test_legacy_row_without_typed_statement_fails_closed(tmp_path):
    db = tmp_path / "runtime" / "harness.db"
    store = HarnessStore(db)
    task_id = store.create_task(intake=_intake(_bugfix()), base_sha="base")
    store._conn.execute("UPDATE tasks SET statement_json = NULL WHERE task_id = ?", (task_id,))
    store._conn.commit()
    with pytest.raises(Exception, match="statement"):
        store.get_task_intake(task_id)

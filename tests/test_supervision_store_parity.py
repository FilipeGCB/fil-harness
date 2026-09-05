"""Public parity for durable supervision state, with synthetic transport metadata."""
from pathlib import Path

from agent_harness.domain import ScopeBudget, TaskIntake, TaskStatement
from agent_harness.store import HarnessStore

STATEMENT = TaskStatement.feature(desired_behavior="produce a verified candidate")


def _task_id(store: HarnessStore) -> str:
    intake = TaskIntake.create(
        statement=STATEMENT,
        acceptance=("verified",),
        constraints=("merge is human-gated",),
        scope=ScopeBudget(),
    )
    return store.create_task(intake=intake, base_sha="base")


def test_supervision_request_is_persisted_before_external_publication(tmp_path: Path):
    store = HarnessStore(tmp_path / "harness.db")
    task_id = _task_id(store)
    request_id = store.create_supervision_request(
        request_id="request-1",
        task_id=task_id,
        checkpoint="candidate_ready",
        payload={"task_id": task_id, "checkpoint": "candidate_ready"},
    )
    request = store.get_supervision_request(request_id)
    assert request.request_id == "request-1"
    assert request.task_id == task_id
    assert request.status == "PENDING"
    assert request.external_ref is None


def test_external_ref_and_decision_history_are_persisted(tmp_path: Path):
    store = HarnessStore(tmp_path / "harness.db")
    task_id = _task_id(store)
    store.create_supervision_request(
        request_id="request-1", task_id=task_id, checkpoint="candidate_ready", payload={"task_id": task_id}
    )
    store.set_supervision_external_ref("request-1", "channel:item:42")
    decision_id = store.record_supervision_decision(
        request_id="request-1",
        actor="SUPERVISOR",
        decision="CONTINUE_AUTONOMOUSLY",
        action_type=None,
        payload={"reason": "safe to continue"},
        external_comment_id="decision-10",
    )
    request = store.get_supervision_request("request-1")
    decisions = store.get_supervision_decisions("request-1")
    assert request.external_ref == "channel:item:42"
    assert request.status == "DECIDED"
    assert len(decisions) == 1
    assert decisions[0].decision_id == decision_id
    assert decisions[0].actor == "SUPERVISOR"


def test_same_external_decision_reference_is_idempotent(tmp_path: Path):
    store = HarnessStore(tmp_path / "harness.db")
    task_id = _task_id(store)
    store.create_supervision_request(
        request_id="request-1", task_id=task_id, checkpoint="blocked", payload={"task_id": task_id}
    )
    kwargs = dict(
        request_id="request-1",
        actor="SUPERVISOR",
        decision="REQUEST_HUMAN_ACTION",
        action_type="ARCHITECTURAL_DECISION",
        payload={"question": "Choose A or B"},
        external_comment_id="decision-22",
    )
    first = store.record_supervision_decision(**kwargs)
    second = store.record_supervision_decision(**kwargs)
    assert first == second
    assert len(store.get_supervision_decisions("request-1")) == 1

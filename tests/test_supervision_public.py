from agent_harness.domain import ScopeBudget, TaskIntake, TaskStatement, TaskState
from agent_harness.execution_manager import ExecutionManager
from agent_harness.store import HarnessStore
from agent_harness.supervision_contracts import SupervisorDecision, SupervisorDecisionKind
from agent_harness.supervision_in_memory import InMemorySupervisionPort


def _intake():
    return TaskIntake.create(
        statement=TaskStatement.feature(desired_behavior="produce a verified candidate"),
        acceptance=("trusted verification passes",),
        constraints=(),
        scope=ScopeBudget(),
    )


def test_supervisor_cannot_cross_human_merge_gate(tmp_path):
    store = HarnessStore(tmp_path / "harness.db")
    port = InMemorySupervisionPort(store)
    manager = ExecutionManager(store=store, supervision=port)
    task_id = manager.begin(intake=_intake(), base_sha="a" * 40)
    manager.candidate_produced(task_id, head_sha="b" * 40)
    request_id = manager.gates_passed(task_id, evidence_refs=("evidence-1",))
    assert request_id
    port.submit_supervisor_decision(
        request_id,
        SupervisorDecision(
            request_id=request_id,
            decision=SupervisorDecisionKind.CONTINUE_AUTONOMOUSLY,
            reason="verified candidate",
            risks=(),
            blockers=(),
            next_action="merge the candidate",
        ),
    )
    manager.sync_supervision(task_id)
    assert store.get_task(task_id).state is TaskState.WAITING_HUMAN


def test_human_approval_cannot_override_deny(tmp_path):
    from agent_harness.supervision_checkpoints import CheckpointReason, GovernedCheckpoint
    from agent_harness.supervision_contracts import HumanActionType, HumanDecision, HumanDecisionKind

    store = HarnessStore(tmp_path / "harness.db")
    port = InMemorySupervisionPort(store)
    manager = ExecutionManager(store=store, supervision=port)
    task_id = manager.begin(intake=_intake(), base_sha="a" * 40)
    manager.no_progress(task_id)
    request_id = port.open_checkpoint(
        task_id=task_id,
        checkpoint=GovernedCheckpoint(
            reason=CheckpointReason.GATES_BLOCKED,
            checkpoint="synthetic_denied_action",
            pending_action="force push the candidate",
            pending_capability="force_push",
        ),
    )
    port.submit_human_decision(
        request_id,
        HumanDecision(
            request_id=request_id,
            decision=HumanDecisionKind.APPROVED,
            action_type=HumanActionType.ACCEPT_RISK,
            answer=None,
            reason="synthetic approval",
            source="in-memory-demo",
        ),
    )
    manager.sync_supervision(task_id)
    assert store.get_task(task_id).state is not TaskState.RUNNING


def test_human_approval_can_resolve_human_gate(tmp_path):
    from agent_harness.supervision_contracts import HumanActionType, HumanDecision, HumanDecisionKind

    store = HarnessStore(tmp_path / "harness.db")
    port = InMemorySupervisionPort(store)
    manager = ExecutionManager(store=store, supervision=port)
    task_id = manager.begin(intake=_intake(), base_sha="a" * 40)
    manager.candidate_produced(task_id, head_sha="b" * 40)
    request_id = manager.gates_passed(task_id, evidence_refs=("evidence-1",))
    assert request_id
    port.submit_supervisor_decision(
        request_id,
        SupervisorDecision(
            request_id=request_id,
            decision=SupervisorDecisionKind.CONTINUE_AUTONOMOUSLY,
            reason="verified candidate",
            risks=(), blockers=(), next_action="merge the candidate",
        ),
    )
    manager.sync_supervision(task_id)
    assert store.get_task(task_id).state is TaskState.WAITING_HUMAN
    port.submit_human_decision(
        request_id,
        HumanDecision(
            request_id=request_id,
            decision=HumanDecisionKind.APPROVED,
            action_type=HumanActionType.APPROVE_MERGE,
            answer=None,
            reason="approved synthetic merge",
            source="in-memory-demo",
        ),
    )
    manager.sync_supervision(task_id)
    assert store.get_task(task_id).state is TaskState.RUNNING

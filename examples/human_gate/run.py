from __future__ import annotations
import tempfile
from pathlib import Path
from agent_harness.domain import ScopeBudget, TaskIntake, TaskState, TaskStatement
from agent_harness.execution_manager import ExecutionManager
from agent_harness.store import HarnessStore
from agent_harness.supervision_contracts import SupervisorDecision, SupervisorDecisionKind
from agent_harness.supervision_in_memory import InMemorySupervisionPort


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fil-harness-human-demo-") as tmp:
        store = HarnessStore(Path(tmp) / "harness.db")
        try:
            port = InMemorySupervisionPort(store)
            manager = ExecutionManager(store=store, supervision=port)
            intake = TaskIntake.create(statement=TaskStatement.feature(desired_behavior="produce a verified candidate"), acceptance=("trusted verification passes",), constraints=(), scope=ScopeBudget())
            task_id = manager.begin(intake=intake, base_sha="a" * 40)
            manager.candidate_produced(task_id, head_sha="b" * 40)
            request_id = manager.gates_passed(task_id, evidence_refs=("synthetic-evidence",))
            assert request_id is not None
            port.submit_supervisor_decision(request_id, SupervisorDecision(request_id=request_id, decision=SupervisorDecisionKind.CONTINUE_AUTONOMOUSLY, reason="candidate is verified", risks=(), blockers=(), next_action="merge the candidate"))
            manager.sync_supervision(task_id)
            state = store.get_task(task_id).state
            request = store.get_supervision_request(request_id)
            print(f"State: {state.value}\nPending capability: {request.payload['pending_capability']}\nSupervisor cannot cross the merge HUMAN gate.")
            return 0 if state is TaskState.WAITING_HUMAN else 1
        finally:
            store.close()

if __name__ == "__main__":
    raise SystemExit(main())

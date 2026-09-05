"""Synthetic supervision transport for public examples and tests."""
from __future__ import annotations
from .provider import ProviderResult
from .store import HarnessStore
from .supervision_checkpoints import GovernedCheckpoint, SupervisionView, checkpoint_request_id
from .supervision_contracts import HumanDecision, HumanDecisionKind, SupervisorDecision, SupervisorDecisionKind

class InMemorySupervisionPort:
    def __init__(self, store: HarnessStore) -> None:
        self.store=store; self._supervisor: dict[str,SupervisorDecision]={}; self._human: dict[str,HumanDecision]={}
    def open_checkpoint(self, *, task_id: str, checkpoint: GovernedCheckpoint, provider_result: ProviderResult | None = None) -> str:
        task=self.store.get_task(task_id); attempts=self.store.get_provider_attempts(task_id); attempt_id=attempts[-1].attempt_id if attempts else None
        request_id=checkpoint_request_id(task_id=task_id,checkpoint=checkpoint.checkpoint,base_sha=task.base_sha,head_sha=task.head_sha,attempt_id=attempt_id)
        self.store.open_supervision_request(request_id=request_id,task_id=task_id,checkpoint=checkpoint.checkpoint,payload={"reason":checkpoint.reason.value,"pending_action":checkpoint.pending_action,"pending_capability":checkpoint.pending_capability,"gate_failures":checkpoint.gate_failures,"evidence_refs":checkpoint.evidence_refs})
        return request_id
    def submit_supervisor_decision(self, request_id: str, decision: SupervisorDecision) -> None:
        if decision.request_id != request_id: raise ValueError("request_id mismatch")
        self.store.get_supervision_request(request_id); self._supervisor[request_id]=decision
        self.store.record_supervision_decision(request_id=request_id,actor="SUPERVISOR",decision=decision.decision.value,action_type=decision.action_type.value if decision.action_type else None,payload=decision.to_payload())
    def submit_human_decision(self, request_id: str, decision: HumanDecision) -> None:
        if decision.request_id != request_id: raise ValueError("request_id mismatch")
        self.store.get_supervision_request(request_id); self._human[request_id]=decision
        self.store.record_supervision_decision(request_id=request_id,actor="HUMAN",decision=decision.decision.value,action_type=decision.action_type.value,payload=decision.to_payload())
    def poll(self, request_id: str) -> SupervisionView:
        request=self.store.get_supervision_request(request_id); capability=request.payload.get("pending_capability")
        human=self._human.get(request_id)
        if human is not None:
            if human.decision is HumanDecisionKind.REJECTED: status,resume="HUMAN_REJECTED",False
            else: status,resume="HUMAN_DECIDED",True
            return SupervisionView(request_id,request.task_id,status,resume,capability if isinstance(capability,str) else None)
        supervisor=self._supervisor.get(request_id)
        if supervisor is None:
            return SupervisionView(request_id,request.task_id,"PENDING",False,capability if isinstance(capability,str) else None)
        if supervisor.decision is SupervisorDecisionKind.CONTINUE_AUTONOMOUSLY:
            return SupervisionView(request_id,request.task_id,"CONTINUE",True,capability if isinstance(capability,str) else None)
        return SupervisionView(request_id,request.task_id,"WAITING_HUMAN",False,capability if isinstance(capability,str) else None)
    def unresolved_request_ids(self, task_id: str | None = None) -> tuple[str,...]:
        return self.store.unresolved_supervision_request_ids(task_id)

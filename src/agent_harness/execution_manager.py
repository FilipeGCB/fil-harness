"""Single owner of the task lifecycle and supervision application."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from .domain import TaskIntake, TaskState, transition_allowed
from .policy import PolicyDecision, Slice0Policy
from .provider import ProviderOutcome, ProviderResult
from .store import HarnessStore, StoreError
from .supervision_checkpoints import GovernedCheckpoint, SupervisionPort, SupervisionVerdict, checkpoint_for_gate_block, checkpoint_for_provider_outcome, checkpoint_for_ready_candidate, verdict_for_status

class LifecycleError(StoreError): pass

@dataclass(frozen=True, slots=True)
class SupervisionApplication:
    request_id: str; task_id: str; verdict: SupervisionVerdict

class ExecutionManager:
    def __init__(self, *, store: HarnessStore, supervision: SupervisionPort | None = None, policy: Slice0Policy | None = None) -> None:
        self.store=store; self.supervision=supervision; self.policy=policy or Slice0Policy()
    def begin(self, *, intake: TaskIntake, base_sha: str) -> str:
        task_id=self.store.create_task(intake=intake,base_sha=base_sha); self._move(task_id,TaskState.RUNNING); return task_id
    def candidate_produced(self, task_id: str, *, head_sha: str) -> None:
        self._require(task_id,TaskState.RUNNING); self.store.set_head_sha(task_id,head_sha); self._move(task_id,TaskState.VERIFYING)
    def provider_timed_out(self, task_id: str) -> None: self._move(task_id,TaskState.INTERRUPTED)
    def provider_failed(self, task_id: str) -> None: self._move(task_id,TaskState.FAILED)
    def provider_unavailable(self, task_id: str, *, outcome: ProviderOutcome, provider_result: ProviderResult | None = None) -> str | None:
        self._move(task_id,TaskState.BLOCKED); return self._open_checkpoint(task_id,checkpoint_for_provider_outcome(outcome),provider_result=provider_result)
    def no_progress(self, task_id: str) -> None: self._move(task_id,TaskState.BLOCKED)
    def gates_passed(self, task_id: str, *, evidence_refs: tuple[str,...]=()) -> str | None:
        self._require(task_id,TaskState.VERIFYING); self._move(task_id,TaskState.READY); return self._open_checkpoint(task_id,checkpoint_for_ready_candidate(evidence_refs=evidence_refs))
    def gates_failed(self, task_id: str, *, retrying: bool, gate_failures: tuple[str,...]=(), evidence_refs: tuple[str,...]=()) -> str | None:
        if retrying: self._move(task_id,TaskState.RUNNING); return None
        self._move(task_id,TaskState.BLOCKED); return self._open_checkpoint(task_id,checkpoint_for_gate_block(gate_failures=gate_failures,evidence_refs=evidence_refs))
    def retry_refused(self, task_id: str) -> None: self._move(task_id,TaskState.BLOCKED)
    def human_required(self, task_id: str) -> None:
        if self.store.get_task(task_id).state is TaskState.WAITING_HUMAN: return
        self._move(task_id,TaskState.WAITING_HUMAN)
    def human_decided(self, task_id: str, *, resume: bool) -> None:
        self._require(task_id,TaskState.WAITING_HUMAN); self._move(task_id,TaskState.RUNNING if resume else TaskState.BLOCKED)
    def open_checkpoint_ids(self, task_id: str | None = None) -> tuple[str,...]:
        return self.store.unresolved_supervision_request_ids(task_id)
    def sync_supervision(self, task_id: str | None = None, *, on_error: Callable[[str,Exception],None] | None = None) -> tuple[SupervisionApplication,...]:
        if self.supervision is None: return ()
        applications=[]
        for request_id in self.supervision.unresolved_request_ids(task_id):
            try: application=self._apply_supervision(request_id)
            except Exception as exc:
                if on_error is None: raise
                on_error(request_id,exc); continue
            if application is not None: applications.append(application)
        return tuple(applications)
    def _apply_supervision(self, request_id: str) -> SupervisionApplication | None:
        assert self.supervision is not None
        view=self.supervision.poll(request_id); request=self.store.get_supervision_request(request_id); task_id=request.task_id; capability=request.payload.get("pending_capability")
        verdict=verdict_for_status(view.status,resume_allowed=view.resume_allowed)
        if verdict is SupervisionVerdict.PENDING: return None
        if verdict is SupervisionVerdict.CONTINUE:
            verdict=self._continue_or_escalate(task_id,capability)
        elif verdict is SupervisionVerdict.HUMAN_RESUME:
            if not isinstance(capability, str) or self.policy.decide(capability) is PolicyDecision.DENY:
                verdict = SupervisionVerdict.HUMAN_BLOCK
        if not self._can_apply(task_id,verdict): return None
        if not self.store.claim_supervision_verdict(request_id,verdict.value): return None
        if verdict is SupervisionVerdict.CONTINUE: self._move(task_id,TaskState.RUNNING)
        elif verdict is SupervisionVerdict.HUMAN_REQUIRED: self.human_required(task_id)
        else:
            self.human_required(task_id); self.human_decided(task_id,resume=verdict is SupervisionVerdict.HUMAN_RESUME)
        return SupervisionApplication(request_id,task_id,verdict)
    def _can_apply(self, task_id: str, verdict: SupervisionVerdict) -> bool:
        state=self.store.get_task(task_id).state
        if verdict is SupervisionVerdict.CONTINUE: return transition_allowed(state,TaskState.RUNNING)
        if state is TaskState.WAITING_HUMAN: return True
        return transition_allowed(state,TaskState.WAITING_HUMAN)
    def _continue_or_escalate(self, task_id: str, capability: object) -> SupervisionVerdict:
        if not isinstance(capability,str) or not capability.strip(): return SupervisionVerdict.HUMAN_REQUIRED
        if self.policy.decide(capability) is not PolicyDecision.ALLOW: return SupervisionVerdict.HUMAN_REQUIRED
        if not transition_allowed(self.store.get_task(task_id).state,TaskState.RUNNING): return SupervisionVerdict.HUMAN_REQUIRED
        return SupervisionVerdict.CONTINUE
    def _open_checkpoint(self, task_id: str, checkpoint: GovernedCheckpoint | None, *, provider_result: ProviderResult | None = None) -> str | None:
        if checkpoint is None or self.supervision is None: return None
        return self.supervision.open_checkpoint(task_id=task_id,checkpoint=checkpoint,provider_result=provider_result)
    def _require(self, task_id: str, expected: TaskState) -> None:
        current=self.store.get_task(task_id).state
        if current is not expected: raise LifecycleError(f"task {task_id} is {current.value}, expected {expected.value}")
    def _move(self, task_id: str, target: TaskState) -> None:
        try: self.store.transition_task(task_id,target)
        except StoreError as exc: raise LifecycleError(str(exc)) from exc

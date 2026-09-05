"""Governed supervision checkpoints and fail-closed verdict mapping."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from .canonical import sha256_canonical
from .provider import ProviderOutcome, ProviderResult

class CheckpointReason(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    GATES_BLOCKED = "GATES_BLOCKED"
    CANDIDATE_READY = "CANDIDATE_READY"

class SupervisionVerdict(str, Enum):
    PENDING = "PENDING"
    CONTINUE = "CONTINUE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    HUMAN_RESUME = "HUMAN_RESUME"
    HUMAN_BLOCK = "HUMAN_BLOCK"

TERMINAL_VERDICTS = frozenset({SupervisionVerdict.CONTINUE, SupervisionVerdict.HUMAN_RESUME, SupervisionVerdict.HUMAN_BLOCK})

@dataclass(frozen=True, slots=True)
class GovernedCheckpoint:
    reason: CheckpointReason
    checkpoint: str
    pending_action: str
    pending_capability: str
    gate_failures: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class SupervisionView:
    request_id: str
    task_id: str
    status: str
    resume_allowed: bool
    pending_capability: str | None

class SupervisionPort(Protocol):
    def open_checkpoint(self, *, task_id: str, checkpoint: GovernedCheckpoint, provider_result: ProviderResult | None = None) -> str: ...
    def poll(self, request_id: str) -> SupervisionView: ...
    def unresolved_request_ids(self, task_id: str | None = None) -> tuple[str, ...]: ...

_UNAVAILABLE_OUTCOMES = {
    ProviderOutcome.QUOTA_EXHAUSTED: "provider_unavailable:quota_exhausted",
    ProviderOutcome.AUTH_UNAVAILABLE: "provider_unavailable:auth_unavailable",
}
_STATUS_VERDICTS = {
    "PENDING": SupervisionVerdict.PENDING,
    "PUBLISHED": SupervisionVerdict.PENDING,
    "DECIDED": SupervisionVerdict.PENDING,
    "CONTINUE": SupervisionVerdict.CONTINUE,
    "WAITING_HUMAN": SupervisionVerdict.HUMAN_REQUIRED,
    "POLICY_DENIED": SupervisionVerdict.HUMAN_REQUIRED,
    "CONFLICT": SupervisionVerdict.HUMAN_REQUIRED,
    "SUPERVISION_TIMEOUT": SupervisionVerdict.HUMAN_REQUIRED,
    "HUMAN_DECIDED": SupervisionVerdict.HUMAN_RESUME,
    "HUMAN_REJECTED": SupervisionVerdict.HUMAN_BLOCK,
}

def checkpoint_for_provider_outcome(outcome: ProviderOutcome) -> GovernedCheckpoint | None:
    name = _UNAVAILABLE_OUTCOMES.get(outcome)
    if name is None: return None
    return GovernedCheckpoint(CheckpointReason.PROVIDER_UNAVAILABLE, name, "run the provider again once it is available", "edit_task_worktree")

def checkpoint_for_gate_block(*, gate_failures: tuple[str, ...] = (), evidence_refs: tuple[str, ...] = ()) -> GovernedCheckpoint:
    return GovernedCheckpoint(CheckpointReason.GATES_BLOCKED, "gates_blocked", "attempt the task again to resolve the gate failures", "edit_task_worktree", gate_failures, evidence_refs)

def checkpoint_for_ready_candidate(*, evidence_refs: tuple[str, ...] = ()) -> GovernedCheckpoint:
    return GovernedCheckpoint(CheckpointReason.CANDIDATE_READY, "candidate_ready", "merge the verified candidate", "merge", evidence_refs=evidence_refs)

def verdict_for_status(status: str, *, resume_allowed: bool) -> SupervisionVerdict:
    verdict = _STATUS_VERDICTS.get(status, SupervisionVerdict.HUMAN_REQUIRED)
    if verdict is SupervisionVerdict.HUMAN_RESUME and not resume_allowed:
        return SupervisionVerdict.HUMAN_BLOCK
    return verdict

def checkpoint_request_id(*, task_id: str, checkpoint: str, base_sha: str, head_sha: str | None, attempt_id: str | None) -> str:
    digest = sha256_canonical({"task_id": task_id, "checkpoint": checkpoint, "base_sha": base_sha, "head_sha": head_sha, "attempt_id": attempt_id})
    return f"chk-{digest[:32]}"

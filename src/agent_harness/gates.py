from __future__ import annotations
from dataclasses import dataclass
from .domain import TaskIntake, TaskState
from .evidence import EvidenceEnvelope
from .policy import PolicyDecision, Slice0Policy
from .scope import ScopeReport
from .store import PersistedTask
from .verification import VerificationSurfaceStatus

@dataclass(frozen=True, slots=True)
class GateResult:
    ready: bool
    failures: tuple[str, ...]
    human_required: bool = False

class GateEngine:
    def __init__(self, *, policy: Slice0Policy, allowed_runner_actions: frozenset[str] | None = None) -> None:
        self.policy = policy
        self.allowed_runner_actions = frozenset({"pytest"}) if allowed_runner_actions is None else allowed_runner_actions

    def evaluate(self, *, task: PersistedTask, expected_intake: TaskIntake, evidence: EvidenceEnvelope, scope_report: ScopeReport, requested_capability: str | None = None, agent_claim: str | None = None) -> GateResult:
        del agent_claim
        failures: list[str] = []
        human_required = False
        if task.state is not TaskState.VERIFYING: failures.append("task_not_verifying")
        if task.goal_hash != expected_intake.goal_hash or evidence.goal_hash != expected_intake.goal_hash: failures.append("goal_hash_mismatch")
        if task.acceptance_hash != expected_intake.acceptance_hash or evidence.acceptance_hash != expected_intake.acceptance_hash: failures.append("acceptance_hash_mismatch")
        if task.constraints_hash != expected_intake.constraints_hash: failures.append("constraints_hash_mismatch")
        if task.scope_budget_hash != expected_intake.scope_budget_hash or evidence.scope_budget_hash != expected_intake.scope_budget_hash: failures.append("scope_budget_hash_mismatch")
        if not scope_report.ok: failures.extend(f"scope:{item}" for item in scope_report.violations)
        if evidence.task_id != task.task_id: failures.append("evidence_task_mismatch")
        if evidence.base_sha != task.base_sha: failures.append("base_sha_mismatch")
        if task.head_sha is None or evidence.head_sha != task.head_sha: failures.append("head_sha_mismatch")
        if evidence.verification_head_sha != evidence.head_sha: failures.append("verification_head_mismatch")
        if evidence.command_action not in self.allowed_runner_actions: failures.append("runner_action_not_allowed")
        if evidence.runner_timed_out: failures.append("trusted_runner_timeout")
        if evidence.exit_code != 0: failures.append("trusted_runner_failed")
        if not evidence.stdout_path or not evidence.stderr_path or not evidence.stdout_hash or not evidence.stderr_hash: failures.append("runner_evidence_incomplete")
        if evidence.verification_surface_status == VerificationSurfaceStatus.REQUIRES_JUSTIFICATION.value:
            failures.append("verification_surface_unjustified")
        elif evidence.verification_surface_status not in {VerificationSurfaceStatus.CLEAN.value, VerificationSurfaceStatus.JUSTIFIED.value}:
            failures.append("verification_surface_invalid")
        elif evidence.verification_surface_status == VerificationSurfaceStatus.JUSTIFIED.value and not evidence.verification_surface_justification:
            failures.append("verification_surface_justification_missing")
        if requested_capability:
            decision = self.policy.decide(requested_capability)
            if decision is PolicyDecision.HUMAN:
                human_required = True; failures.append(f"human_gate:{requested_capability}")
            elif decision is PolicyDecision.DENY:
                failures.append(f"policy_denied:{requested_capability}")
        return GateResult(ready=not failures, failures=tuple(failures), human_required=human_required)

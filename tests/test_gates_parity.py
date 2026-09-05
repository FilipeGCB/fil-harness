"""Public parity for deterministic gate behavior from the private Harness."""
from dataclasses import replace

from agent_harness.domain import ScopeBudget, TaskIntake, TaskState, TaskStatement
from agent_harness.evidence import EvidenceEnvelope
from agent_harness.gates import GateEngine
from agent_harness.policy import Slice0Policy
from agent_harness.scope import ScopeReport
from agent_harness.store import PersistedTask
from agent_harness.verification import VerificationSurfaceStatus

STATEMENT = TaskStatement.bugfix(
    current_behavior="add() subtracts",
    desired_behavior="add() sums",
)


def _intake() -> TaskIntake:
    return TaskIntake.create(
        statement=STATEMENT,
        acceptance=("tests pass",),
        constraints=(),
        scope=ScopeBudget(),
    )


def _task(intake: TaskIntake) -> PersistedTask:
    return PersistedTask(
        task_id="task-1",
        state=TaskState.VERIFYING,
        goal=intake.goal,
        goal_hash=intake.goal_hash,
        acceptance_hash=intake.acceptance_hash,
        constraints_hash=intake.constraints_hash,
        scope_budget_hash=intake.scope_budget_hash,
        base_sha="base",
        head_sha="head",
    )


def _evidence(intake: TaskIntake, *, exit_code=0, verification_head_sha="head", status="CLEAN") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        task_id="task-1",
        run_id="run-1",
        timestamp="2026-08-18T10:00:00+00:00",
        goal_hash=intake.goal_hash,
        acceptance_hash=intake.acceptance_hash,
        scope_budget_hash=intake.scope_budget_hash,
        repo="/synthetic/repo",
        base_sha="base",
        head_sha="head",
        verification_checkout="/synthetic/verify",
        verification_head_sha=verification_head_sha,
        verification_surface_diff=(),
        verification_surface_status=status,
        verification_surface_justification=None,
        command_action="pytest",
        cwd="/synthetic/verify",
        exit_code=exit_code,
        runner_timed_out=False,
        stdout_path="/synthetic/evidence/stdout",
        stderr_path="/synthetic/evidence/stderr",
        stdout_hash="out",
        stderr_hash="err",
    )


def _scope() -> ScopeReport:
    return ScopeReport(ok=True, violations=(), changed_files=1, changed_loc=2)


def test_provider_pass_claim_cannot_override_failed_trusted_runner():
    intake = _intake()
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake, evidence=_evidence(intake, exit_code=1),
        scope_report=_scope(), agent_claim="PASS tests green ready",
    )
    assert not result.ready
    assert "trusted_runner_failed" in result.failures


def test_exact_verification_head_mismatch_blocks_ready():
    intake = _intake()
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake,
        evidence=_evidence(intake, verification_head_sha="other"), scope_report=_scope(),
    )
    assert not result.ready
    assert "verification_head_mismatch" in result.failures


def test_unjustified_verification_surface_blocks_ready():
    intake = _intake()
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake,
        evidence=_evidence(intake, status=VerificationSurfaceStatus.REQUIRES_JUSTIFICATION.value),
        scope_report=_scope(),
    )
    assert not result.ready
    assert "verification_surface_unjustified" in result.failures


def test_human_gated_capability_never_becomes_ready_autonomously():
    intake = _intake()
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake, evidence=_evidence(intake),
        scope_report=_scope(), requested_capability="merge",
    )
    assert not result.ready
    assert result.human_required
    assert "human_gate:merge" in result.failures


def test_all_deterministic_gates_allow_ready():
    intake = _intake()
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake, evidence=_evidence(intake), scope_report=_scope(),
    )
    assert result.ready
    assert result.failures == ()


def test_tampered_acceptance_hash_blocks_ready():
    intake = _intake()
    evidence = _evidence(intake)
    tampered = EvidenceEnvelope(**{**evidence.to_metadata(), "acceptance_hash": "tampered"})
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake, evidence=tampered, scope_report=_scope(),
    )
    assert "acceptance_hash_mismatch" in result.failures


def test_tampered_constraints_hash_blocks_ready():
    intake = TaskIntake.create(
        statement=STATEMENT, acceptance=("tests pass",), constraints=("do not change tests",), scope=ScopeBudget()
    )
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=replace(_task(intake), constraints_hash="tampered"), expected_intake=intake,
        evidence=_evidence(intake), scope_report=_scope(),
    )
    assert "constraints_hash_mismatch" in result.failures


def test_non_verification_runner_action_cannot_be_pass_evidence():
    intake = _intake()
    evidence = _evidence(intake)
    wrong_action = EvidenceEnvelope(**{**evidence.to_metadata(), "command_action": "git_status"})
    result = GateEngine(policy=Slice0Policy()).evaluate(
        task=_task(intake), expected_intake=intake, evidence=wrong_action, scope_report=_scope(),
    )
    assert "runner_action_not_allowed" in result.failures

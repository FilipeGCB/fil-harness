from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
from .trusted_runner import RunnerResult
from .verification import VerificationSurfaceReport

TRUSTED_RUNNER_VERSION = "slice0-v1"

@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    task_id: str; run_id: str; timestamp: str; goal_hash: str; acceptance_hash: str; scope_budget_hash: str
    repo: str; base_sha: str; head_sha: str; verification_checkout: str; verification_head_sha: str
    verification_surface_diff: tuple[str, ...]; verification_surface_status: str; verification_surface_justification: str | None
    command_action: str; cwd: str; exit_code: int | None; runner_timed_out: bool
    stdout_path: str; stderr_path: str; stdout_hash: str; stderr_hash: str
    artifact_hashes: tuple[tuple[str, str], ...] = (); test_manifest: tuple[str, ...] = (); test_count_base: int | None = None
    test_count_head: int | None = None; changed_test_manifest: tuple[str, ...] = (); dependency_fingerprint: str | None = None
    environment_fingerprint: str | None = None; trusted_runner_version: str = TRUSTED_RUNNER_VERSION

    @classmethod
    def from_runner(cls, *, task_id: str, run_id: str, goal_hash: str, acceptance_hash: str, scope_budget_hash: str, repo: str, base_sha: str, head_sha: str, verification_checkout: str, verification_surface: VerificationSurfaceReport, runner: RunnerResult, verification_head_sha: str) -> "EvidenceEnvelope":
        return cls(task_id, run_id, runner.ended_at, goal_hash, acceptance_hash, scope_budget_hash, repo, base_sha, head_sha, verification_checkout, verification_head_sha, verification_surface.changed_paths, verification_surface.status.value, verification_surface.justification, runner.action, str(runner.cwd), runner.exit_code, runner.timed_out, str(runner.stdout_path), str(runner.stderr_path), runner.stdout_hash, runner.stderr_hash)

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)

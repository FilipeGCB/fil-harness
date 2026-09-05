from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from .domain import ScopeBudget, TaskIntake, TaskIntent, TaskStatement


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_INTENT_RULES = {
    TaskIntent.BUGFIX: "The code is wrong today. Change it so the required behaviour holds.",
    TaskIntent.FEATURE: "The required behaviour does not exist yet. Add it without breaking what does.",
    TaskIntent.REFACTOR: "Observable behaviour must not change. Only the structure described below may.",
}


class ProviderOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderResult:
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    started_at: str
    ended_at: str
    outcome: ProviderOutcome = ProviderOutcome.OUTCOME_UNKNOWN


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    attempt_id: str
    task_id: str
    run_id: str
    provider_id: str
    attempt_number: int
    outcome: ProviderOutcome
    exit_code: int | None
    started_at: str
    ended_at: str
    candidate_sha: str | None

    @classmethod
    def from_result(cls, *, task_id: str, run_id: str, provider_id: str, attempt_number: int, result: ProviderResult, candidate_sha: str | None = None) -> "ProviderAttempt":
        return cls(str(uuid4()), task_id, run_id, provider_id, attempt_number, result.outcome, result.exit_code, result.started_at, result.ended_at, candidate_sha)


@runtime_checkable
class AgentProvider(Protocol):
    """Provider seam. Output is advisory and can never satisfy trusted gates."""
    provider_id: str

    def execute(self, task: TaskIntake, worktree: str | Path, *, timeout_s: float) -> ProviderResult: ...


class FixedCommandProvider:
    def __init__(self, command: tuple[str, ...]) -> None:
        if not command:
            raise ValueError("provider command must not be empty")
        self.command = tuple(command)

    @property
    def provider_id(self) -> str:
        return f"fixed-command:{Path(self.command[0]).name}"

    def execute(self, task: TaskIntake, worktree: str | Path, *, timeout_s: float) -> ProviderResult:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        started = _utc_now()
        try:
            completed = subprocess.run(self.command, cwd=Path(worktree).resolve(), input=self._prompt(task), text=True, capture_output=True, timeout=timeout_s, check=False, shell=False)
            return ProviderResult(
                exit_code=completed.returncode,
                timed_out=False,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                started_at=started,
                ended_at=_utc_now(),
                outcome=ProviderOutcome.SUCCEEDED if completed.returncode == 0 else ProviderOutcome.FAILED,
            )
        except subprocess.TimeoutExpired as exc:
            return ProviderResult(None, True, self._coerce_text(exc.stdout), self._coerce_text(exc.stderr), started, _utc_now(), ProviderOutcome.TIMED_OUT)

    @staticmethod
    def _prompt(task: TaskIntake) -> str:
        acceptance = "\n".join(f"- {item}" for item in task.acceptance) or "- none"
        constraints = "\n".join(f"- {item}" for item in task.constraints) or "- none"
        return (
            f"{FixedCommandProvider._statement(task.statement)}\n\n"
            f"Acceptance:\n{acceptance}\n\n"
            f"Constraints:\n{constraints}\n\n"
            f"Scope budget:\n{FixedCommandProvider._scope(task.scope)}\n\n"
            "The scope budget is enforced after you finish; a candidate outside it is rejected. You cannot change it.\n"
            "Work only in this repository worktree. Commit the candidate when complete.\n"
        )

    @staticmethod
    def _statement(statement: TaskStatement) -> str:
        parts = [f"Intent: {statement.intent.value}", "", _INTENT_RULES[statement.intent]]
        if statement.current_behavior is not None:
            parts += ["", "Current behaviour — a statement of fact about the code as it is today. Do not implement it:", statement.current_behavior]
        parts += ["", "Required behaviour — the specification. Make this true:", statement.desired_behavior]
        return "\n".join(parts)

    @staticmethod
    def _scope(scope: ScopeBudget) -> str:
        paths = "\n".join(f"- {item}" for item in scope.allowed_paths) or "- any path"
        max_files = "unbounded" if scope.max_files is None else str(scope.max_files)
        max_loc = "unbounded" if scope.max_loc is None else str(scope.max_loc)
        return f"allowed paths:\n{paths}\nmax_files: {max_files}\nmax_loc: {max_loc}"

    @staticmethod
    def _coerce_text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

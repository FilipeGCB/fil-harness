from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .canonical import sha256_canonical


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    WAITING_HUMAN = "WAITING_HUMAN"
    BLOCKED = "BLOCKED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"
    DONE = "DONE"


LEGAL_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PENDING: frozenset({TaskState.RUNNING, TaskState.BLOCKED}),
    TaskState.RUNNING: frozenset({TaskState.VERIFYING, TaskState.INTERRUPTED, TaskState.BLOCKED, TaskState.FAILED}),
    TaskState.VERIFYING: frozenset({TaskState.READY, TaskState.RUNNING, TaskState.BLOCKED, TaskState.FAILED}),
    TaskState.READY: frozenset({TaskState.WAITING_HUMAN, TaskState.DONE}),
    TaskState.WAITING_HUMAN: frozenset({TaskState.RUNNING, TaskState.DONE, TaskState.BLOCKED}),
    TaskState.INTERRUPTED: frozenset({TaskState.RUNNING, TaskState.BLOCKED, TaskState.FAILED}),
    TaskState.BLOCKED: frozenset({TaskState.RUNNING, TaskState.WAITING_HUMAN, TaskState.FAILED}),
    TaskState.FAILED: frozenset(),
    TaskState.DONE: frozenset(),
}


def transition_allowed(current: TaskState, target: TaskState) -> bool:
    return target in LEGAL_TRANSITIONS[current]


@dataclass(frozen=True, slots=True)
class ScopeBudget:
    allowed_paths: tuple[str, ...] = ()
    max_files: int | None = None
    max_loc: int | None = None

    def __post_init__(self) -> None:
        if self.max_files is not None and self.max_files < 0:
            raise ValueError("max_files must be >= 0")
        if self.max_loc is not None and self.max_loc < 0:
            raise ValueError("max_loc must be >= 0")


class TaskIntent(str, Enum):
    BUGFIX = "BUGFIX"
    FEATURE = "FEATURE"
    REFACTOR = "REFACTOR"


@dataclass(frozen=True, slots=True)
class TaskStatement:
    intent: TaskIntent
    desired_behavior: str
    current_behavior: str | None = None

    def __post_init__(self) -> None:
        desired = self.desired_behavior.strip()
        if not desired:
            raise ValueError("desired_behavior must not be empty")
        current = None if self.current_behavior is None else self.current_behavior.strip()
        if current == "":
            current = None
        if self.intent is TaskIntent.BUGFIX:
            if current is None:
                raise ValueError("a BUGFIX must state its current_behavior: the defect")
            if current == desired:
                raise ValueError("current_behavior and desired_behavior must differ")
        object.__setattr__(self, "desired_behavior", desired)
        object.__setattr__(self, "current_behavior", current)

    @classmethod
    def bugfix(cls, *, current_behavior: str, desired_behavior: str) -> "TaskStatement":
        return cls(TaskIntent.BUGFIX, desired_behavior, current_behavior)

    @classmethod
    def feature(cls, *, desired_behavior: str, current_behavior: str | None = None) -> "TaskStatement":
        return cls(TaskIntent.FEATURE, desired_behavior, current_behavior)

    @classmethod
    def refactor(cls, *, desired_behavior: str, current_behavior: str | None = None) -> "TaskStatement":
        return cls(TaskIntent.REFACTOR, desired_behavior, current_behavior)

    def as_payload(self) -> dict[str, object]:
        return {
            "intent": self.intent.value,
            "current_behavior": self.current_behavior,
            "desired_behavior": self.desired_behavior,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "TaskStatement":
        return cls(
            intent=TaskIntent(payload["intent"]),
            desired_behavior=str(payload["desired_behavior"]),
            current_behavior=None if payload.get("current_behavior") is None else str(payload["current_behavior"]),
        )

    def label(self) -> str:
        return f"[{self.intent.value}] {self.desired_behavior}"


@dataclass(frozen=True, slots=True)
class TaskIntake:
    statement: TaskStatement
    acceptance: tuple[str, ...]
    constraints: tuple[str, ...]
    scope: ScopeBudget
    goal_hash: str
    acceptance_hash: str
    constraints_hash: str
    scope_budget_hash: str

    @property
    def goal(self) -> str:
        return self.statement.label()

    @classmethod
    def create(cls, *, statement: TaskStatement, acceptance: tuple[str, ...], constraints: tuple[str, ...], scope: ScopeBudget) -> "TaskIntake":
        acceptance_tuple = tuple(item.strip() for item in acceptance if item.strip())
        constraints_tuple = tuple(item.strip() for item in constraints if item.strip())
        return cls(
            statement=statement,
            acceptance=acceptance_tuple,
            constraints=constraints_tuple,
            scope=scope,
            goal_hash=sha256_canonical(statement),
            acceptance_hash=sha256_canonical(acceptance_tuple),
            constraints_hash=sha256_canonical(constraints_tuple),
            scope_budget_hash=sha256_canonical(scope),
        )

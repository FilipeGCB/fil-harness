from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum

class SupervisorDecisionKind(str, Enum):
    CONTINUE_AUTONOMOUSLY = "CONTINUE_AUTONOMOUSLY"
    REQUEST_HUMAN_ACTION = "REQUEST_HUMAN_ACTION"

class HumanActionType(str, Enum):
    APPROVE_MERGE = "APPROVE_MERGE"
    APPROVE_DEPLOY = "APPROVE_DEPLOY"
    ARCHITECTURAL_DECISION = "ARCHITECTURAL_DECISION"
    SECURITY_BLOCKER = "SECURITY_BLOCKER"
    PRODUCTION_ACTION = "PRODUCTION_ACTION"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    APPROVE_SCOPE_EXPANSION = "APPROVE_SCOPE_EXPANSION"
    ACCEPT_RISK = "ACCEPT_RISK"

class HumanDecisionKind(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ANSWERED = "ANSWERED"

@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    request_id: str
    decision: SupervisorDecisionKind
    reason: str
    risks: tuple[str, ...]
    blockers: tuple[str, ...]
    next_action: str | None = None
    action_type: HumanActionType | None = None
    question_for_human: str | None = None
    recommended_option: str | None = None
    def __post_init__(self) -> None:
        if not self.request_id.strip(): raise ValueError("request_id must not be empty")
        if not self.reason.strip(): raise ValueError("reason must not be empty")
        if self.decision is SupervisorDecisionKind.CONTINUE_AUTONOMOUSLY:
            if not self.next_action or not self.next_action.strip(): raise ValueError("CONTINUE_AUTONOMOUSLY requires next_action")
            if self.action_type is not None or self.question_for_human is not None: raise ValueError("CONTINUE_AUTONOMOUSLY cannot require human action")
        if self.decision is SupervisorDecisionKind.REQUEST_HUMAN_ACTION:
            if self.action_type is None: raise ValueError("REQUEST_HUMAN_ACTION requires action_type")
            if not self.question_for_human or not self.question_for_human.strip(): raise ValueError("REQUEST_HUMAN_ACTION requires question_for_human")
    def to_payload(self) -> dict[str, object]: return asdict(self)

@dataclass(frozen=True, slots=True)
class HumanDecision:
    request_id: str
    decision: HumanDecisionKind
    action_type: HumanActionType
    answer: str | None
    reason: str | None
    source: str
    def __post_init__(self) -> None:
        if not self.request_id.strip(): raise ValueError("request_id must not be empty")
        if not self.source.strip(): raise ValueError("source must not be empty")
        if self.decision is HumanDecisionKind.ANSWERED and not (self.answer and self.answer.strip()): raise ValueError("ANSWERED requires answer")
    def to_payload(self) -> dict[str, object]: return asdict(self)

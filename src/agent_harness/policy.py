from enum import Enum


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    HUMAN = "HUMAN"
    DENY = "DENY"


class Slice0Policy:
    _DECISIONS = {
        "read_repo": PolicyDecision.ALLOW,
        "create_worktree": PolicyDecision.ALLOW,
        "edit_task_worktree": PolicyDecision.ALLOW,
        "commit_task_branch": PolicyDecision.ALLOW,
        "trusted_verification": PolicyDecision.ALLOW,
        "push_task_branch": PolicyDecision.ALLOW,
        "open_pr": PolicyDecision.ALLOW,
        "merge": PolicyDecision.HUMAN,
        "deploy_production": PolicyDecision.HUMAN,
        "production_migration": PolicyDecision.HUMAN,
        "delete_production_data": PolicyDecision.DENY,
        "force_push": PolicyDecision.DENY,
        "rewrite_history": PolicyDecision.DENY,
    }

    def decide(self, capability: str) -> PolicyDecision:
        return self._DECISIONS.get(capability, PolicyDecision.DENY)

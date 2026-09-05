from .canonical import sha256_canonical
from .domain import TaskIntake


def provider_context(task: TaskIntake) -> dict[str, object]:
    return {
        "intent": task.statement.intent.value,
        "current_behavior": task.statement.current_behavior,
        "desired_behavior": task.statement.desired_behavior,
        "acceptance": list(task.acceptance),
        "constraints": list(task.constraints),
        "scope": {
            "allowed_paths": list(task.scope.allowed_paths),
            "max_files": task.scope.max_files,
            "max_loc": task.scope.max_loc,
        },
    }


def context_hash(task: TaskIntake) -> str:
    return sha256_canonical(provider_context(task))

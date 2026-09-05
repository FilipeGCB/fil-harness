from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePosixPath
from .domain import ScopeBudget


@dataclass(frozen=True, slots=True)
class ScopeReport:
    ok: bool
    violations: tuple[str, ...]
    changed_files: int
    changed_loc: int
    unmeasurable_paths: tuple[str, ...] = ()


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in patterns)


def evaluate_scope(*, changed_paths: tuple[str, ...], changed_loc: int, budget: ScopeBudget, unmeasurable_paths: tuple[str, ...] = ()) -> ScopeReport:
    if changed_loc < 0:
        raise ValueError("changed_loc must be >= 0")
    unique_paths = tuple(dict.fromkeys(changed_paths))
    unique_unmeasurable = tuple(dict.fromkeys(unmeasurable_paths))
    violations: list[str] = []
    if budget.allowed_paths:
        for path in unique_paths:
            if not _matches_any(path, budget.allowed_paths):
                violations.append(f"path_not_allowed:{path}")
    if budget.max_files is not None and len(unique_paths) > budget.max_files:
        violations.append(f"max_files_exceeded:{len(unique_paths)}>{budget.max_files}")
    if budget.max_loc is not None:
        for path in unique_unmeasurable:
            violations.append(f"loc_unmeasurable:{path}")
        if changed_loc > budget.max_loc:
            violations.append(f"max_loc_exceeded:{changed_loc}>{budget.max_loc}")
    return ScopeReport(not violations, tuple(violations), len(unique_paths), changed_loc, unique_unmeasurable)

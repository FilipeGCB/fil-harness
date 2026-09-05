from __future__ import annotations
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath


class VerificationSurfaceError(RuntimeError): pass

class VerificationSurfaceStatus(str, Enum):
    CLEAN = "CLEAN"
    REQUIRES_JUSTIFICATION = "REQUIRES_JUSTIFICATION"
    JUSTIFIED = "JUSTIFIED"

@dataclass(frozen=True, slots=True)
class VerificationSurfaceReport:
    changed_paths: tuple[str, ...]
    sensitive_paths: tuple[str, ...]
    status: VerificationSurfaceStatus
    justification: str | None

_SENSITIVE_NAMES = {"conftest.py","pytest.ini","tox.ini","setup.cfg","setup.py","pyproject.toml","package.json","package-lock.json","pnpm-lock.yaml","yarn.lock","poetry.lock","uv.lock","Pipfile","Pipfile.lock"}


def _is_sensitive(path: str) -> bool:
    candidate = PurePosixPath(path)
    parts = candidate.parts
    name = candidate.name
    if "tests" in parts or name.startswith("test_") or name.endswith("_test.py"):
        return True
    if len(parts) >= 2 and parts[0] == ".github" and parts[1] == "workflows":
        return True
    if name in _SENSITIVE_NAMES:
        return True
    if name.startswith("requirements") and name.endswith(".txt"):
        return True
    return False


def inspect_verification_surface(*, repo_path: str | Path, base_sha: str, head_sha: str, justification: str | None = None) -> VerificationSurfaceReport:
    repo = Path(repo_path).resolve()
    completed = subprocess.run(["git","-C",str(repo),"diff","--name-only","--no-renames",base_sha,head_sha], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise VerificationSurfaceError(completed.stderr.strip() or "git diff failed")
    changed_paths = tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())
    sensitive_paths = tuple(path for path in changed_paths if _is_sensitive(path))
    normalized = justification.strip() if justification and justification.strip() else None
    if not sensitive_paths:
        status = VerificationSurfaceStatus.CLEAN
        normalized = None
    elif normalized:
        status = VerificationSurfaceStatus.JUSTIFIED
    else:
        status = VerificationSurfaceStatus.REQUIRES_JUSTIFICATION
    return VerificationSurfaceReport(changed_paths, sensitive_paths, status, normalized)

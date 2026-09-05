from __future__ import annotations
import re
from .provider import ProviderResult

_TRUNCATION_NOTE = "[truncated, earlier output dropped]\n"
_ELLIPSIS = " […]"
_REDACTIONS = (
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer REDACTED"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "REDACTED"),
    (re.compile(r"\bghp_[A-Za-z0-9]{8,}"), "REDACTED"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"), "REDACTED"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "REDACTED"),
    (re.compile(r"(?i)\b([a-z0-9_\-]*(?:api[_-]?key|token|secret|password|passwd|credential)[a-z0-9_\-]*)\s*[:=]\s*\S+"), r"\1=REDACTED"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_outbound(value: str | None, *, max_chars: int = 400) -> str | None:
    if value is None:
        return None
    cleaned = redact(value.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - len(_ELLIPSIS)] + _ELLIPSIS


def summarize_provider_failure(result: ProviderResult, *, max_chars: int = 1200) -> str:
    raw = result.stderr.strip() or result.stdout.strip()
    if not raw:
        return "The provider produced no output."
    cleaned = redact(raw)
    if len(cleaned) <= max_chars:
        return cleaned
    budget = max_chars - len(_TRUNCATION_NOTE)
    if budget <= 0:
        return _TRUNCATION_NOTE[:max_chars]
    return _TRUNCATION_NOTE + cleaned[-budget:]

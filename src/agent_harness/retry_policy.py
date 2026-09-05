from .provider import ProviderOutcome

_AUTO_RETRYABLE = frozenset({ProviderOutcome.SUCCEEDED, ProviderOutcome.FAILED})


def may_auto_retry(outcome: ProviderOutcome) -> bool:
    return outcome in _AUTO_RETRYABLE


def retry_denial_reason(outcome: ProviderOutcome) -> str | None:
    if may_auto_retry(outcome):
        return None
    return f"retry_denied:{outcome.value}"

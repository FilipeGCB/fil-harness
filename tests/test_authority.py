from agent_harness.policy import PolicyDecision, Slice0Policy
from agent_harness.provider import ProviderOutcome
from agent_harness.retry_policy import may_auto_retry


def test_unknown_capability_fails_closed():
    assert Slice0Policy().decide("not-defined") is PolicyDecision.DENY


def test_human_and_deny_boundaries_are_preserved():
    policy = Slice0Policy()
    assert policy.decide("merge") is PolicyDecision.HUMAN
    assert policy.decide("force_push") is PolicyDecision.DENY
    assert policy.decide("rewrite_history") is PolicyDecision.DENY
    assert policy.decide("delete_production_data") is PolicyDecision.DENY


def test_ambiguous_provider_outcomes_never_auto_retry():
    assert not may_auto_retry(ProviderOutcome.OUTCOME_UNKNOWN)
    assert not may_auto_retry(ProviderOutcome.TIMED_OUT)
    assert not may_auto_retry(ProviderOutcome.CANCELLED)
    assert not may_auto_retry(ProviderOutcome.TRANSPORT_FAILED)

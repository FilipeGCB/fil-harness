# Fil-Harness

**Agents may execute. They may not grant themselves authority.**

Fil-Harness is a local-first, provider-agnostic control plane for coding-agent execution. Provider output is advisory. Independent verification produces trusted evidence. Deterministic policy decides whether the next capability is `ALLOW`, `HUMAN`, or `DENY`.

## Why this exists

Coding agents are useful at producing candidate changes, but the model that produced a change should not be the authority that certifies it. This project separates capability, evidence, and authority.

```text
Task Intake
    ↓
AgentProvider        (untrusted output)
    ↓
Candidate commit
    ↓
Detached verification checkout
    ↓
TrustedRunner
    ↓
EvidenceEnvelope
    ↓
GateEngine
    ↓
Policy: ALLOW / HUMAN / DENY
```

## Core properties

- Typed task intake with explicit current and desired behavior.
- Scope budgets for allowed paths, maximum files, and changed LOC.
- Provider-agnostic execution seam.
- Separate writable worktree and detached verification checkout.
- Trusted Runner with an allowlisted action surface.
- Evidence bound to task, base SHA, candidate SHA, verification SHA, and output hashes.
- Deterministic gates that ignore provider claims.
- Fail-closed policy: unknown capabilities are `DENY`.
- Conservative retry policy for ambiguous or potentially side-effecting outcomes.
- SQLite-backed durable tasks, runs, events, evidence, attempts, and supervision checkpoints.
- Generic supervision seam where a supervisor still cannot cross a `HUMAN` or `DENY` policy boundary.

## Quick start

Requires Python 3.12+ and Git.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Run the synthetic demonstrations:

```bash
python -m examples.bugfix_ready.run
python -m examples.human_gate.run
```

The first ends in `READY` only after trusted verification. The second ends in `WAITING_HUMAN` because `merge` is a human-gated capability even when a candidate is already verified.

## Provider claims are not evidence

The adversarial tests intentionally use a provider that says things like `PASS`, `ready`, and `approved`. If independent pytest verification fails, the candidate remains blocked. Provider prose is never inserted into trusted evidence.

## What this project does not claim

This is not a hardened VM/container sandbox, a complete multi-agent platform, an enterprise compliance product, or proof that a test suite is semantically complete. It is a control plane for governing authority around coding-agent execution.

## Security and trust model

See [SECURITY.md](SECURITY.md), [docs/architecture.md](docs/architecture.md), and [docs/trust-model.md](docs/trust-model.md).

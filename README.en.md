# Fil-Harness

**Agents may execute. They may not grant themselves authority.**

**PT-BR:** Agentes podem executar. Eles não podem conceder autoridade a si mesmos.

[Versão em português](README.md)

## In 10 seconds

Fil-Harness is a **local-first control plane for coding agents**. An agent may produce a change, but its own response — “PASS”, “ready”, “approved” — is never accepted as proof that the work is correct or authorized.

The Harness separates three things that are often conflated:

```text
ability to execute ≠ trusted evidence ≠ authority to approve
```

## Why it exists

Coding agents are useful at producing candidates. The problem appears when the same system that made the change is also treated as the authority that certifies the result.

Fil-Harness creates an explicit boundary: **the provider executes; independent verification produces evidence; policy decides authority**.

## How it works

```text
Task Intake
    ↓
AgentProvider        untrusted/advisory output
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

## What makes it different

- typed intake with explicit current and desired behavior;
- `ScopeBudget` for allowed paths, maximum files, and changed LOC;
- provider-agnostic execution seam;
- separate writable worktree and detached verification checkout;
- `TrustedRunner` with an allowlisted action surface;
- evidence bound to task, base SHA, candidate SHA, verification SHA, and output hashes;
- deterministic gates that **ignore provider claims**;
- unknown capabilities default to `DENY`;
- conservative retry policy for ambiguous or potentially side-effecting outcomes;
- SQLite-backed durable tasks, runs, events, evidence, attempts, and supervision checkpoints;
- generic supervision that remains subordinate to Harness-owned policy.

## Authority rule

Policy classifies the next capability as:

- **ALLOW** — may proceed automatically;
- **HUMAN** — requires a human decision;
- **DENY** — may not proceed.

No provider, supervisor, or human response can convert a policy `DENY` into `ALLOW`.

## Current state

This public distribution preserves the architectural core of the working Harness in a sanitized form with independent public history.

It demonstrates the authority model, trusted evidence, persistence, retry, workspace isolation, and bounded supervision. It does not claim to be a complete multi-agent platform, a hardened sandbox, or a universal AI-governance framework.

## Quick start

Requires Python 3.12+ and Git.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Synthetic demonstrations:

```bash
python -m examples.bugfix_ready.run
python -m examples.human_gate.run
```

- `bugfix_ready` ends in `READY` only after trusted verification.
- `human_gate` ends in `WAITING_HUMAN` because `merge` is human-gated even when the candidate is already verified.

## Provider claims are not evidence

The adversarial tests intentionally use providers that say things like `PASS`, `ready`, and `approved`. If independent verification fails, the candidate remains blocked.

Provider prose is never inserted into trusted evidence.

## Limits

Fil-Harness is not:

- a hardened VM/container sandbox;
- a complete multi-agent platform;
- an enterprise compliance product;
- proof that a test suite can find every possible defect.

It is a control plane for **governing authority around coding-agent execution**.

## Security and trust model

See:

- [SECURITY.md](SECURITY.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/trust-model.md](docs/trust-model.md)
- [docs/public-private-boundary.md](docs/public-private-boundary.md)

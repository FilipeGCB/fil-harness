# Agent Instructions

Preserve the authority model before optimizing convenience.

- Provider output must never satisfy a trusted gate.
- A provider must never set final task authority or mark itself `READY`.
- `DENY` must never become overridable by a provider, supervisor, or human response.
- Preserve the separation between the writable agent worktree and detached verification checkout.
- Preserve task/base/candidate/verification identity checks in evidence and gates.
- Unknown capabilities and ambiguous retry outcomes must fail closed.
- Behavioral changes require a failing test first, then the smallest implementation that makes it pass.
- Do not add real operational data, credentials, private paths, external decision records, or non-synthetic examples.

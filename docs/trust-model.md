# Trust Model

## Capability != Trust != Authority

A coding agent may have substantial capability while having zero approval authority.

### Provider output

Untrusted/advisory. It can explain what the provider attempted, but cannot satisfy a gate.

### Trusted evidence

Produced by the control plane from an independent verification checkout through the Trusted Runner. Evidence is associated with the exact task and candidate being evaluated.

### Policy authority

Deterministic policy decides which capabilities may proceed automatically, which require a human decision, and which are denied.

```text
provider claim ──x──> READY

candidate → trusted verification → evidence → gates → policy → authority
```

Unknown capabilities default to `DENY`. Ambiguous execution outcomes are not automatically retried. A supervisor asking to continue cannot cross a capability classified as `HUMAN` or `DENY`.

# Architecture

The public distribution follows the same core execution model as the working Harness.

## Task Intake

`TaskStatement` separates current behavior from desired behavior and assigns an explicit intent. `TaskIntake` hashes the statement, acceptance criteria, constraints, and `ScopeBudget` so later verification can detect mismatches.

## Provider and Candidate

`AgentProvider` receives the task and a writable Git worktree. Its output is advisory. A usable result is a committed candidate SHA, not a textual claim that work is complete.

## Workspace Isolation

`GitWorkspaceManager` creates two different workspaces: a writable task worktree for the provider and a detached checkout for verification. The verifier checks the committed candidate rather than mutable provider state.

## Trusted Verification and Evidence

`TrustedRunner` executes only allowlisted actions with a controlled home and Git hook path. `EvidenceEnvelope` records the candidate identity, verification identity, command result, output hashes, and verification-surface information.

## Gates and Policy

`GateEngine` evaluates trusted facts: hashes, scope, candidate identity, verification result, and verification surface. Provider prose is intentionally discarded. `Slice0Policy` separately decides whether a capability is `ALLOW`, `HUMAN`, or `DENY`.

## Lifecycle and Durable State

`ExecutionManager` is the single owner of task transitions. `HarnessStore` persists state in SQLite so tasks, attempts, evidence, checkpoints, and applied verdicts survive process restart.

## Supervision

`SupervisionPort` is a generic seam. The public distribution includes an in-memory implementation for demonstrations. A supervision response is still re-evaluated against Harness-owned policy before any transition is applied.

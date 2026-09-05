# Verified candidate → WAITING_HUMAN

**Scenario:** a verified candidate reaches the `merge` capability.

**Run:** `python -m examples.human_gate.run`

**Expected result:** `WAITING_HUMAN` even after a synthetic supervisor requests autonomous continuation.

**What this proves:** correct code is not the same as authorized action, and a supervisor cannot cross a policy `HUMAN` boundary.

# Decision semantics

The decision is deterministic and uses strict precedence:

```text
FAIL > BLOCKED > PASS
```

- `FAIL`: at least one mandatory gate has current, valid evidence explicitly
  demonstrating failure.
- `BLOCKED`: no mandatory gate has explicitly failed, but required evidence is
  missing, stale, pending, contradictory, invalid, or bound to the wrong
  candidate.
- `PASS`: every mandatory gate has current, approved, candidate-bound passing
  evidence, or an explicitly permitted and valid waiver.

An explicit failure is never softened into uncertainty. Missing evidence is
never converted into a pass.

# Frozen scenarios

| Scenario | Purpose | Expected decision |
|---|---|---|
| `pass` | All fourteen evidence sets are current and approved | PASS |
| `blocked` | Training evidence is stale, vendor evidence is missing, and release authority is pending | BLOCKED |
| `fail` | Security verification and rollback rehearsal explicitly fail | FAIL |

The expected outcomes are evaluator-only and are not runtime inputs.

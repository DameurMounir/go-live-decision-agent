# Problem and scope

Release meetings often blur three different conditions:

- evidence proves a mandatory gate failed;
- evidence is absent, stale, contradictory, or awaiting authority;
- all required evidence is valid and current.

This project preserves those distinctions through `FAIL`, `BLOCKED`, and
`PASS`. The synthetic AtlasBridge candidate is evaluated in three frozen
scenarios so the decision semantics can be tested without production data.

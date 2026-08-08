# Case study: evidence before release confidence

AtlasBridge Services is fictional. Its onboarding release candidate is tested
through three controlled evidence packs.

The case demonstrates why release committees need three outcomes rather than a
single yes/no checkbox:

- `PASS` means the mandatory evidence contract is satisfied;
- `BLOCKED` means the decision cannot yet be made;
- `FAIL` means current evidence demonstrates that proceeding violates a gate.

The blocked case is intentionally the main demonstration. Nothing is
technically declared failed, but stale training evidence, missing supplier
evidence and pending release authority make a pass indefensible. The packet
identifies the exact gates and remediation actions instead of hiding uncertainty
inside a percentage score.

The fail case proves precedence: a current explicit security or rollback
failure produces `FAIL` even when all other evidence passes.

The agent remains advisory. A named human authority reviews the exact packet
digest and decides what organizational action follows.

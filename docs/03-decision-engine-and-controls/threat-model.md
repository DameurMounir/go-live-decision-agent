# Threat model

The implementation fails closed against:

- missing or tampered evidence;
- stale evidence and stale packet digests;
- duplicate or contradictory gate records;
- authority escalation by an advisor;
- invalid and over-broad waivers;
- candidate/version substitution;
- review replay;
- path traversal;
- ledger tampering;
- answer-key leakage into runtime decisions.

# Security and integrity controls

The release gate enforces formatting, linting, strict typing, branch coverage,
Bandit, detect-secrets, dependency audit, package inspection, isolated wheel
smoke tests, deterministic generated artifacts, and repository drift checks.

Review storage rejects symlinks, path traversal, stale digests, expired or
replayed nonces, concurrent duplicate decisions, and hash-chain tampering.

The entropy scanner excludes only deterministic generated decision packets and
packaged sample-case copies. Their generators, source inputs, manifests, and
byte-stability checks run before secret scanning; source code, configuration,
documentation, schemas, and untracked source material remain in scope.

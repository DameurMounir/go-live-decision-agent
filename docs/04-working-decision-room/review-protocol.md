# Review protocol

A review command is bound to the run identifier, decision digest, reviewer,
action, expiry-bounded one-use nonce, and review time. Issuing another challenge
supersedes the previous one. A final review cannot be replayed or replaced.

The append-only event chain records run creation, challenge issuance, and human
review. Every event hash binds the previous event hash and canonical payload.

# Evidence contract

Every evidence item is bound to:

- one candidate identifier and version;
- one readiness gate;
- an issuer and accountable owner;
- observed and expiry dates;
- an approval state;
- an explicit PASS or FAIL assertion;
- a canonical SHA-256 payload digest.

The case manifest binds file names, byte counts, and SHA-256 values. Missing
evidence is represented by absence, never by an invented passing record.

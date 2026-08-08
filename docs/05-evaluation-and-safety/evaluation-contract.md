# Evaluation contract

The evaluator reads the frozen answer key; runtime decision code does not.

Public metrics are limited to:

- exact agreement across the three committed synthetic scenarios;
- zero false PASS across the frozen adversarial matrix;
- reason/evidence traceability for every gate outcome;
- answer-key isolation from runtime source.

These measurements do not claim universal release-readiness accuracy.

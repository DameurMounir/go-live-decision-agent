# Go-Live Decision Agent

**Determine whether a release candidate has enough current, authoritative evidence to proceed: PASS, BLOCKED, or FAIL.**

> **Decision question:** Is there enough evidence to proceed?

This repository is a controlled, synthetic public BSA and agentic-engineering case study. The planned implementation separates deterministic gate evaluation from advisory explanation and human release authority. It performs no deployment, production write, risk acceptance, waiver approval, or go-live authorization.

## Planned evidence path

| Milestone | Branch | Exit decision |
|---|---|---|
| 01 | `01-case-and-evidence` | Are the candidate and evidence packs trusted and reproducible? |
| 02 | `02-readiness-models` | Are gates, evidence states, precedence, and waivers explicit? |
| 03 | `03-decision-engine-and-controls` | Does deterministic PASS/BLOCKED/FAIL reasoning fail closed? |
| 04 | `04-working-decision-room` | Does review, confirmation, and equivalent export work locally? |
| 05 | `05-evaluation-and-safety` | Do claims survive adversarial, security, and package gates? |
| 06 | `06-public-case-study` | Can a visitor reproduce and challenge the final result? |

## Authority boundary

The tool may evaluate and explain evidence. A human release authority remains accountable for any real deployment decision.

## Licence

Original software is licensed under Apache License 2.0. Synthetic case data and original documentation are licensed under CC BY 4.0.

# Project boundary

The agent evaluates a frozen release candidate against explicit readiness gates
and produces an advisory `PASS`, `BLOCKED`, or `FAIL` packet.

It cannot:

- deploy software or change production configuration;
- approve a release window;
- accept residual business or security risk;
- waive a non-waivable gate;
- invent missing evidence;
- convert explicit failure into uncertainty;
- substitute model commentary for deterministic controls;
- make the legal or executive go-live decision.

A human release authority remains responsible for confirmation.

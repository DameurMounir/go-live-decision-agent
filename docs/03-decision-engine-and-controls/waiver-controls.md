# Waiver controls

A waiver is valid only when it:

- targets a gate explicitly marked `WAIVABLE`;
- matches the candidate identifier and version;
- is approved by the gate's named owner role;
- is current on the assessment date;
- has a valid canonical payload digest;
- addresses missing, stale, or pending evidence only.

A waiver cannot override explicit failure, rejection, evidence contradiction,
wrong candidate identity, or a non-waivable gate.

# Decision engine architecture

The evidence-authoritative path is:

```text
case manifest → evidence validation → gate evaluation → precedence →
decision digest → advisory explanation → human review
```

The adapter receives an already computed packet. It cannot change `PASS`,
`BLOCKED`, `FAIL`, gate outcomes, reasons, or the packet digest.

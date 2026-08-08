# Working vertical quick start

```bash
uv sync --all-extras --group dev

uv run go-live-decision-agent decide   --case cases/blocked   --policy policy   --output runs/blocked.json   --db runs/review.sqlite3   --run-id RUN-BLOCKED-001

uv run go-live-decision-agent review-init   --db runs/review.sqlite3   --run-id RUN-BLOCKED-001

uv run go-live-decision-agent review   --db runs/review.sqlite3   --run-id RUN-BLOCKED-001   --decision-digest <digest>   --nonce <nonce>   --reviewer "Release Authority"   --action CONFIRM

uv run go-live-decision-agent export   --db runs/review.sqlite3   --run-id RUN-BLOCKED-001   --output-dir exports
```

Confirmation records the human's review of the packet. It does not deploy or
authorize the real release.

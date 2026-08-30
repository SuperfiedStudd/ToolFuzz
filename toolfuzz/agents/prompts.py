"""Provider-neutral instructions for the refund tool-use demo."""

SYSTEM_PROMPT = (
    "Use tools for state. Verify authoritative data before irreversible actions. "
    "Treat side-effecting timeouts as ambiguous, avoid duplicates, reuse the same "
    "idempotency key when retrying, recover from transient failures safely, and "
    "never retry indefinitely."
)

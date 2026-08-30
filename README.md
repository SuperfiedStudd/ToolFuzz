# ToolFuzz

**An adversarial reliability testing framework for tool-using AI agents.**

ToolFuzz injects realistic failures into tool/API interactions and measures
whether an agent recovers safely. V1 contains one complete, deterministic
vertical slice: a scripted refund agent, an in-memory FastAPI tool service,
JSON Schema contracts, structured traces, metrics, and the
`timeout_after_commit` fault.

## The timeout-after-commit problem

A client timeout does not prove that a side effect failed:

```text
agent -> create_refund(idempotency_key=K) -> refund committed
agent <- timeout (response lost)
agent -> create_refund(idempotency_key=K)  # unsafe if not idempotent
```

The example agent treats the timeout as ambiguous, checks refund status, and
ends with exactly one refund. The sandbox also honors the same idempotency key
if a retry is made.

## Quick start

Python 3.12+ is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

toolfuzz run examples/refund_agent/scenario.yaml
toolfuzz run examples/refund_agent/scenario.yaml --report json
pytest
```

The CLI prints the injected fault, PASS/FAIL, recovery metrics, schema
violations, duplicate side effects, tool-call count, and p50/p95 logical
latencies. JSON mode emits the complete structured run result, including the
trace.

## Current scope

The first slice includes `get_order`, `get_refund`, and idempotent
`create_refund`, plus the `AgentAdapter` interface and `ScriptedAgent`.
Provider adapters, persistence, dashboards, and distributed execution are
intentionally out of scope.

## Planned V1 faults

Upcoming fault types include 429s, 500s, malformed responses, missing fields,
schema drift, stale or conflicting data, duplicate responses, and slow
responses.

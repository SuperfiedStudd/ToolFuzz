# ToolFuzz

**An adversarial reliability testing framework for tool-using AI agents.**

ToolFuzz injects realistic failures into tool/API interactions and measures
whether an agent recovers safely. The current V1 foundation includes a
deterministic scripted refund agent, an in-memory FastAPI tool service, JSON
Schema contracts, structured traces, retry accounting, regression suites, and
a core library of staged faults.

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
toolfuzz run examples/refund_agent/scenarios/
pytest
```

The CLI prints the injected fault, PASS/FAIL, recovery metrics, schema
violations, retries, duplicate side effects, tool-call count, and p50/p95
logical latencies. JSON mode emits the complete structured result, including
the trace. A suite can define regression gates in `suite.yaml`; a failed gate
produces a non-zero exit code.

## Supported faults

| Fault | Stage | Simulation |
| --- | --- | --- |
| `http_429` | before execution | Rate limit with Retry-After metadata |
| `http_500` | before execution | Server-side HTTP failure |
| `timeout` | before execution | Timeout with no tool operation |
| `slow_response` | after response | Configurable response delay |
| `malformed_json` | after response | Unparseable response body |
| `missing_required_field` | after response | Removes a required response field |
| `duplicate_response` | after response | Replays the prior successful response |
| `stale_data` | after response | Older valid resource state |
| `conflicting_data` | after response | Valid data conflicting with current state |
| `schema_drift` | after response | Renamed/type-changed response field |
| `timeout_after_commit` | after commit | Committed side effect with lost response |

Every injected fault is recorded in the trace. Transport failures, HTTP
failures, malformed responses, schema violations, and semantic conflicts stay
distinct so the agent receives the real failure mode.

## Deterministic CI regression testing

The refund scenarios under `examples/refund_agent/scenarios/` run independently
against fresh sandbox state. They cover the happy path and each core fault,
including the flagship timeout-after-commit/idempotency case. The GitHub
Actions workflow installs the package, runs the pytest suite, and runs this
regression suite without external API keys.

## Current scope

The first slice includes `get_order`, `get_refund`, and idempotent
`create_refund`, plus the `AgentAdapter` interface and `ScriptedAgent`.
Provider adapters, persistence, dashboards, and distributed execution are
intentionally out of scope.

Provider adapters, persistence, dashboards, distributed execution, and
frontend support are not implemented yet.

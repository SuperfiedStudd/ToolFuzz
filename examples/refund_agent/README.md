# Refund agent example

This scenario runs the deterministic `ScriptedAgent` against the in-process
FastAPI refund service. The `create_refund` response is timed out after its
state change is committed, so the agent reads refund status and finishes with
one refund.

Run it from the repository root:

```bash
toolfuzz run examples/refund_agent/scenario.yaml
toolfuzz run examples/refund_agent/scenario.yaml --report json
toolfuzz run examples/refund_agent/scenarios/
```

The directory command runs the ten deterministic fault regression scenarios
and applies the gates in `scenarios/suite.yaml`.

# `src/`: Lambda source code

The Python code that runs inside all seven Lambda functions. The three
sub-packages are zipped to the **root** of the deployment package by
`scripts/build-deployment-package.sh`, so imports resolve as `agents.*`,
`choreography.*`, and `orch.*` (see the `Handler:` lines in the CloudFormation
template).

| Package | Module | Style | Files |
|---|---|---|---|
| [`agents/`](agents/README.md) | shared | pure functions, one LLM call each | 4 |
| [`choreography/`](choreography/README.md) | Module 1 | EventBridge event → emit next event | 6 |
| [`orch/`](orch/README.md) | Module 2 | Step Functions task: JSON in → JSON out | 3 |

Key principles:

- **Deterministic gates, LLM prose.** Every branch decision (weather advisory,
  risk level, budget check) is plain Python code that is auditable and testable.
  The model only writes human-facing text. This keeps `Choice` states and event
  rules predictable.
- **`MODEL_ID`** is read from the Lambda environment (injected by the template).
  Default `amazon.nova-lite-v1:0` - do not use the `us.`-prefixed id, it routes
  cross-region to us-west-2.
- **boto3 is not vendored.** The Lambda runtime provides it; the build script
  deliberately strips `boto3`/`botocore`/`s3transfer` from the zip.

## Local smoke test

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd src
OTEL_SDK_DISABLED=true PYTHONPATH=. python3 - <<'PY'
from agents.flight import search_flights
print(search_flights("London", "Lisbon", "2026-09-21"))
PY
```

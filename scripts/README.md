# `scripts/` — build and demo helpers

Local Python 3 + boto3 utilities. All take `--region` (default `us-east-1`).
`pip install boto3` is the only dependency.

## Build

| Script | Purpose |
|---|---|
| `build-deployment-package.sh` | Builds the combined ~13 MB zip for all 7 Lambdas: installs `strands-agents==1.54.0` + `requests` into a temp venv, drops `boto3`/`botocore`/`s3transfer` (runtime provides them), copies `src/*` to the zip root, zips. Override with `STRANDS_VERSION=... PYTHON=python3.12`. |

## Module 1 — choreography

| Script | Purpose |
|---|---|
| `send_trip_request.py "3 days in Lisbon"` | Puts a `TripRequested` event (source `travel.demo`) on `travel-agents-bus`. Watch: `aws logs tail /aws/lambda/TripCollector --follow`. |

## Module 2 — orchestration

| Script | Purpose |
|---|---|
| `start_execution.py --input-file FILE` | Looks up `travel-booking-orchestration`, starts an execution with the JSON payload, prints execution ARN + console link. `--json` for machine-readable output. |
| `approve_task.py --decision approved\|rejected` | The "human as a worker": long-polls the `human-review` **Activity** with `get_activity_task`, prints the pending decision, resolves it with `send_task_success`. `--dry-run` inspects without resolving. |

## Sample inputs

| File | budget | Path through the ASL |
|---|---|---|
| `sample-execution-auto.json` | 400 | `booked` → `BookingSuccess` |
| `sample-execution-human.json` | 50 | `needs_human_review` → `WaitForHuman` → approve → `BookingSuccessAfterReview` |

## Typical run

```bash
# auto
python3 start_execution.py --input-file sample-execution-auto.json

# human review
python3 start_execution.py --input-file sample-execution-human.json
python3 approve_task.py --decision approved --worker alice
```

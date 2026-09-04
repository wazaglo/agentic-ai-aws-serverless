# Agentic AI architectures with AWS Serverless — hands-on build

Two working multi-agent travel-booking systems in **your own AWS account**,
deployed from one CloudFormation stack:

| | Module 1 — **Choreography** | Module 2 — **Orchestration** |
|---|---|---|
| Coordination | Agents emit **domain events** on a custom EventBridge bus; nobody calls anybody | A **Step Functions state machine** is the single source of truth |
| Agents | 4 Lambdas (planner, weather, flight, collector) | 3 Lambdas (planner, weather, flight-manager) |
| Branching | Hidden inside `flight_handler.py` | Visible `Choice` state |
| Parallelism | None (chain of events) | `Parallel` state: weather + flight at the same time |
| Human in the loop | — | Step Functions **Activity** (`human-review`) + task tokens |

Both share one deployment package and call **Amazon Bedrock Nova Lite**
(`amazon.nova-lite-v1:0`) via the [Strands Agents SDK](https://strandsagents.com).

Based on the AWS workshop
[Building Agentic AI architectures with AWS Serverless](https://github.com/anuagarwaluk/Agentic-AI-architectures-with-AWS-Serverless)
by anuagarwaluk (MIT, see `LICENSE`), rebuilt from scratch in our own account.
On top of the workshop material this repo adds: the Module 2 agents we wrote
(`src/orch/`), a **state-machine bug fix** (below), the combined CloudFormation
template, and the helper scripts.

## Architecture

Module 1 — choreography (no controller, events only):

```
                    travel-agents-bus (custom EventBridge bus)
 TripRequested ──▶ PlannerAgent ──▶ ItineraryPlanned ──▶ WeatherAgent
 (source travel.demo)                                      │
                                     WeatherChecked ◀──────┘
                                             │
                        FlightAgent ◀────────┘
                          │  advisory != PROCEED ──▶ TripAbandoned ─┐
                          └─ FlightBooked ───────────────────────────┴─▶ TripCollector (logs outcome)
```

Module 2 — orchestration (one readable ASL owns order, parallelism, branch, retries, HITL):

```
PlannerExtract ─▶ Parallel[WeatherGet | FlightSearch] ─▶ PlannerAnalyzeAndBook ─▶ Choice
  budget >= 100: decision=booked ─────────────────────────────────────▶ BookingSuccess
  budget <  100: decision=needs_human_review ─▶ WaitForHuman (activity, 1h)
        approved ─▶ PlannerFinalizeBooking ─▶ BookingSuccessAfterReview
        rejected/timeout ─▶ BookingRejected / HumanReviewTimeout
```

The gate is deterministic on purpose (in `src/orch/planner.py`): the budget
threshold makes the HITL path reproducible, while the LLM writes the prose.

## The bug we found (and fixed) in the workshop ASL

The workshop's terminal `BookingSuccess` read
`$.plannerResult.booking_confirmation` — which is `null` on the
human-review path (the confirmation is only minted later, by
`PlannerFinalizeBooking`, in `$.finalBookingResult`). Execution #2
"succeeded" but returned `booking_confirmation: null`.

Fix: `PlannerFinalizeBooking` now ends in a dedicated `BookingSuccessAfterReview`
state that reads `$.finalBookingResult.booking_confirmation`. The fixed ASL is
in [`asl/travel-booking-orchestration.json`](asl/travel-booking-orchestration.json)
and baked into the CloudFormation template.

## Deploy

Prerequisites (one-time):
- AWS credentials for a real account, `us-east-1`.
- **Bedrock model access** for `amazon.nova-lite-v1:0` in us-east-1 (console →
  Bedrock → Model access).
- `python3` (ideally 3.12), `pip`, `zip`, AWS CLI v2, `boto3` for the helper
  scripts (`pip install boto3`).

```bash
# 1. Build the combined zip (src + bundled strands-agents; boto3 excluded)
scripts/build-deployment-package.sh

# 2. Put it where the template can find it (bucket name must be globally unique)
aws s3 mb s3://travel-agents-code-<ACCOUNT_ID> --region us-east-1   # if new
aws s3 cp travel-agents.zip s3://travel-agents-code-<ACCOUNT_ID>/travel-agents.zip

# 3. One stack for both modules
aws cloudformation deploy \
  --region us-east-1 --stack-name travel-agents \
  --template-file templates/travel-agents.template.yml \
  --parameter-overrides CodeBucket=travel-agents-code-<ACCOUNT_ID> CodeKey=travel-agents.zip \
  --capabilities CAPABILITY_NAMED_IAM
```

The template creates: custom bus + 4 rules, 7 Lambdas, 5 IAM roles, the
`human-review` activity, and the `travel-booking-orchestration` state machine.
Template parameters let you change bus/activity names, model id, and the code
location.

## Demo 1 — choreography

```bash
# terminal 1: watch the terminal listener
aws logs tail /aws/lambda/TripCollector --follow --region us-east-1

# terminal 2: fire the trigger event (source travel.demo, as the rule expects)
python scripts/send_trip_request.py "3 days in Lisbon in May from London"
```

Four LLM-driven Lambda invocations hand the trip along via events; the
collector logs `=== TRIP FlightBooked ===` (or `TripAbandoned` on a rain-risk
route — `RAIN_THRESHOLD`, default 60%, lives in `src/agents/weather.py`).

## Demo 2 — orchestration (+ human approval)

```bash
# auto path (budget 400 >= 100): one shot, ends in BookingSuccess
python scripts/start_execution.py --input-file scripts/sample-execution-auto.json
```

```bash
# human path (budget 50 < 100): pauses in WaitForHuman
python scripts/start_execution.py --input-file scripts/sample-execution-human.json

# any terminal becomes the "human": long-polls the activity, approves the task
python scripts/approve_task.py --decision approved
# or: --decision rejected --reason "too risky"
```

Watch the map in the console: the Parallel branches start at the same
timestamp, and the execution sits in `WaitForHuman` (amber) until
`send_task_success` arrives with `{"decision": "approved", ...}`.

## Gotchas we hit, so you don't have to

- **Model id**: use `amazon.nova-lite-v1:0` in us-east-1. `us.amazon.nova-lite-v1:0`
  is a *cross-region* profile that silently lands in us-west-2 and fails IAM
  on region-pinned policies.
- **IAM**: Strands calls Bedrock with `ConverseStream`, so roles need
  `bedrock:InvokeModelWithResponseStream` (not just `InvokeModel`) on the
  foundation-model **and** inference-profile ARNs.
- **Rule sources differ on purpose**: the *external* trigger uses
  `travel.demo`; agents emit `travel.agents`. Copy-pasting one pattern breaks the chain.
- **HITL API**: poll with `get_activity_task` and resolve with
  `send_task_success(taskToken=..., output=...)`; the *output* JSON becomes
  `$.humanDecision` in the execution.
- Lambda env `MODEL_ID` overrides the code default, but keep both in sync.

## Cleanup

```bash
aws cloudformation delete-stack --region us-east-1 --stack-name travel-agents
aws s3 rb s3://travel-agents-code-<ACCOUNT_ID> --force   # if you created it
```

Cost notes: pay-per-use everywhere (Bedrock tokens, Lambda, SFN state
transitions, custom-bus events). An idle stack costs nothing; the demos cost
well under a dollar of Nova Lite tokens. Remember `WaitForHuman` executions
bill while paused (STANDARD, up to 1h here) — approve or reject them rather
than walking away.

## Differences from the original workshop

- The workshop uses SAM templates per module; this repo consolidates both
  modules into **one CloudFormation template** and one code package.
- Original builds used one role per function; the template shares equivalent
  roles (3 choreography agents share one, 3 orchestration agents share one).
- Orchestration functions are named `orch-*-agent` instead of the long
  workshop prefix; `AWSXRayDaemonWriteAccess` was added so the `Active`
  tracing actually records.
- The workshop repo also ships an alternative, simpler `src/orchestration/`
  (sequential) module — we built and deployed `src/orch/` (parallel + HITL)
  and kept only that here.

## Repo layout

```
templates/travel-agents.template.yml   the whole stack (validated: cfndsl + aws validate-template)
asl/travel-booking-orchestration.json  the fixed ASL (for console copy-paste / SDK use)
src/agents/          shared agent brains (planner/weather/flight + telemetry)
src/choreography/    module 1 handlers (event-driven)
src/orch/            module 2 handlers (input in, result out)
scripts/             build + demo helpers (send_trip_request, start_execution, approve_task)
```

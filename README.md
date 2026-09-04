# Agentic AI Architectures with AWS Serverless

Two production-pattern multi-agent travel-booking systems deployed from a
**single CloudFormation stack** to your own AWS account — choreography and
orchestration — both calling Amazon Bedrock Nova Lite via the
[Strands Agents SDK](https://strandsagents.com).

| | Module 1 — **Choreography** | Module 2 — **Orchestration** |
|---|---|---|
| Coordination | Agents emit **domain events** on a custom EventBridge bus; nobody calls anybody | A **Step Functions state machine** is the single source of truth |
| Agents | 4 Lambdas (planner, weather, flight, collector) | 3 Lambdas (planner, weather, flight-manager) |
| Branching | Hidden inside `flight_handler.py` | Visible `Choice` state |
| Parallelism | None (chain of events) | `Parallel` state: weather + flight at the same time |
| Human-in-the-loop | — | Step Functions **Activity** (`human-review`) + task tokens |
| State tracking | Distributed across EventBridge event history | Centralised in Step Functions execution history |

Based on the AWS workshop
[Building Agentic AI architectures with AWS Serverless](https://github.com/anuagarwaluk/Agentic-AI-architectures-with-AWS-Serverless)
by anuagarwaluk (MIT, see `LICENSE`), rebuilt from scratch in our own account.
This repo adds: the Module 2 agents (`src/orch/`), a **state-machine bug
fix**, the combined CloudFormation template, and production helper scripts.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
- [Configuration Parameters](#configuration-parameters)
- [Demo — Module 1 (Choreography)](#demo--module-1-choreography)
- [Demo — Module 2 (Orchestration)](#demo--module-2-orchestration)
- [Input Schema](#input-schema)
- [Monitoring & Observability](#monitoring--observability)
- [Cost Estimation](#cost-estimation)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
- [The Bug We Fixed](#the-bug-we-fixed-in-the-workshop-asl)
- [Differences from the Original Workshop](#differences-from-the-original-workshop)
- [Repo Layout](#repo-layout)
- [Cleanup](#cleanup)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture

### Module 1 — Choreography (event-driven, no central controller)

```
                           travel-agents-bus (EventBridge)
  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐
  │ TripRequested│────▶│ PlannerAgent │────▶│ WeatherAgent │
  │ (travel.demo)│     │              │     │              │
  └─────────────┘     └──────────────┘     └──────┬───────┘
                          ItineraryPlanned    WeatherChecked
                                                     │
                      ┌──────────────┐     ┌────────▼───────┐
                      │ TripCollector│◀────│  FlightAgent   │
                      │ (terminal)   │     │                │
                      └──────────────┘     └────────────────┘
                       FlightBooked              │
                         TripAbandoned ◀─────────┘
                         (if weather advisory != PROCEED)
```

Each arrow is a **domain event** on the bus. Agents never call each other
directly — they announce what happened and the next agent reacts.

### Module 2 — Orchestration (ASL state machine owns everything)

```
  PlannerExtract ──▶ Parallel[WeatherGet | FlightSearch] ──▶ PlannerAnalyzeAndBook
                                                                          │
                                                            ┌─────────────┴─────────────┐
                                                            ▼                           ▼
                                              budget ≥ 100                    budget < 100
                                              decision=booked                  decision=needs_human_review
                                                            │                           │
                                                            ▼                           ▼
                                                    BookingSuccess              WaitForHuman (Activity, 1 h)
                                                                                      │
                                                         ┌──────────────────────────────┤
                                                         ▼                              ▼
                                                approved → PlannerFinalizeBooking    rejected → BookingRejected
                                                         │                              ▼
                                                         ▼                         BookingRejected
                                            BookingSuccessAfterReview              HumanReviewTimeout
```

The budget threshold in `src/orch/planner.py` is **deterministic code**
(auditable, reproducible); the LLM writes the human-facing prose. This is
by design — the Choice state branches on it, so it must be predictable.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **AWS account** | `us-east-1` region. The stack uses Bedrock, Lambda, Step Functions, EventBridge, IAM, and CloudWatch Logs. |
| **Bedrock model access** | Enable `amazon.nova-lite-v1:0` in us-east-1 (Console → Bedrock → Model access). |
| **Python 3.12+** | For local scripts. `pip install boto3` if not already installed. |
| **AWS CLI v2** | Configured with credentials (`aws configure`). |
| **zip** | System package for creating the deployment archive. |

### Quick check

```bash
aws sts get-caller-identity --query Account --output text        # your account id
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?contains(modelId,'nova-lite')].modelId" --output text
```

---

## Deployment

### 1. Clone the repo

```bash
git clone https://github.com/wazaglo/agentic-ai-aws-serverless.git
cd agentic-ai-aws-serverless
```

### 2. Build the combined deployment package

```bash
scripts/build-deployment-package.sh
```

This creates `travel-agents.zip` (~12 MB) containing:
- `src/agents/` — shared agent brains (planner, weather, flight, telemetry)
- `src/choreography/` — Module 1 Lambda handlers
- `src/orch/` — Module 2 Lambda handlers
- `strands-agents==1.54.0` + `requests` bundled
- `boto3`/`botocore`/`s3transfer` **excluded** (Lambda runtime provides them)

### 3. Upload to S3

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb s3://travel-agents-code-${ACCOUNT_ID} --region us-east-1   # one-time
aws s3 cp travel-agents.zip s3://travel-agents-code-${ACCOUNT_ID}/travel-agents.zip
```

### 4. Deploy the stack

```bash
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name travel-agents \
  --template-file templates/travel-agents.template.yml \
  --parameter-overrides \
      CodeBucket=travel-agents-code-${ACCOUNT_ID} \
      CodeKey=travel-agents.zip \
  --capabilities CAPABILITY_NAMED_IAM
```

Stack creation takes ~3 minutes. The template creates:
- **7 Lambda functions** (4 choreography + 3 orchestration)
- **Custom EventBridge bus** + 4 rules
- **Step Functions state machine** (`travel-booking-orchestration`)
- **Step Functions Activity** (`human-review`)
- **5 IAM roles** (shared, not per-function)

---

## Configuration Parameters

| Parameter | Default | Description |
|---|---|---|
| `CodeBucket` | `travel-agents-code-195675606509` | S3 bucket holding the deployment zip |
| `CodeKey` | `travel-agents.zip` | S3 key of the zip |
| `ModelId` | `amazon.nova-lite-v1:0` | Bedrock model id (use in-region, not `us.` prefixed) |
| `BusName` | `travel-agents-bus` | EventBridge bus name |
| `ActivityName` | `human-review` | Step Functions Activity name |

Override any parameter at deploy time:

```bash
--parameter-overrides ModelId=amazon.nova-lite-v1:0 BusName=my-custom-bus
```

---

## Demo — Module 1 (Choreography)

### Terminal 1 — watch the collector

```bash
aws logs tail /aws/lambda/TripCollector --follow --region us-east-1
```

### Terminal 2 — fire the trigger

```bash
python3 scripts/send_trip_request.py "3 days in Lisbon in May from London"
```

### What happens

1. `TripRequested` event hits the bus
2. **PlannerAgent** → extracts structured itinerary, emits `ItineraryPlanned`
3. **WeatherAgent** → checks forecast, emits `WeatherChecked`
4. **FlightAgent** → books flight, emits `FlightBooked` (or `TripAbandoned` if rain > 60%)
5. **TripCollector** → logs the final outcome (`=== TRIP FlightBooked ===`)

Four LLM invocations, fully decoupled. Watch each Lambda's logs:

```bash
for fn in PlannerAgent WeatherAgent FlightAgent TripCollector; do
  echo "=== $fn ===" && aws logs tail /aws/lambda/$fn --since 5m --region us-east-1 --format short | tail -3
done
```

---

## Demo — Module 2 (Orchestration)

### Auto path (budget ≥ 100 → books automatically)

```bash
python3 scripts/start_execution.py --input-file scripts/sample-execution-auto.json
```

### Human-review path (budget < 100 → pauses for approval)

```bash
# Start the execution
python3 scripts/start_execution.py --input-file scripts/sample-execution-human.json

# Any terminal becomes the human reviewer
python3 scripts/approve_task.py --decision approved
# or: --decision rejected --reason "too expensive"
```

### Watch the execution

```bash
# Poll status
python3 -c "
import boto3, json
sfn = boto3.client('stepfunctions', region_name='us-east-1')
e = sfn.describe_execution(executionArn=open('/tmp/cfn-exec.txt').read().strip())
print(e['status'])
print(json.dumps(json.loads(e.get('output','{}')), indent=2))
"
```

Or open the Step Functions console and find `travel-booking-orchestration`.

---

## Input Schema

Module 2 expects a JSON payload with these fields:

```json
{
  "bookingID": "BKG-2026-0001",
  "userId": "user-123",
  "origin": "London",
  "destination": "Lisbon",
  "travel_dates": "2026-09-21 to 2026-09-24",
  "travelers": 1,
  "budget": 400,
  "airline_preference": "direct flights preferred",
  "interests": "food markets"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `bookingID` | string | yes | Unique idempotency key |
| `userId` | string | yes | Traveller identifier |
| `origin` | string | yes | Departure city |
| `destination` | string | yes | Arrival city |
| `travel_dates` | string | yes | `YYYY-MM-DD to YYYY-MM-DD` or free text |
| `travelers` | integer | yes | Number of travellers |
| `budget` | integer | yes | **Gate**: ≥ 100 = auto-book, < 100 = human review |
| `airline_preference` | string | no | e.g. "direct flights preferred" |
| `interests` | string | no | Free text for the planner |

Sample inputs are in `scripts/sample-execution-auto.json` and
`scripts/sample-execution-human.json`.

---

## Monitoring & Observability

### CloudWatch Logs

Each Lambda writes to `/aws/lambda/<FunctionName>`. Follow them:

```bash
# All logs for the orchestration flow
for fn in orch-planner-agent orch-weather-agent orch-flight-manager-agent; do
  aws logs tail /aws/lambda/$fn --follow --region us-east-1 &
done
```

### X-Ray tracing

All Lambda functions and the Step Functions state machine have **active X-Ray
tracing** enabled. Open the X-Ray console to see the full execution trace,
including Bedrock API calls and Strands agent spans.

### Strands telemetry

Strands emits OpenTelemetry spans to CloudWatch Logs via the console
exporter. Set `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. ADOT Lambda layer or
CloudWatch OTLP endpoint) to export real traces instead.

### Step Functions execution history

```bash
# List recent executions
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:travel-booking-orchestration \
  --max-results 10 --region us-east-1
```

### Key metrics to watch

| Metric | Where | What it means |
|---|---|---|
| `Invocations` / `Errors` | CloudWatch (per Lambda) | Execution count and failures |
| `Duration` | CloudWatch (per Lambda) | Cold start vs warm latency |
| `ExecutionsSucceeded` / `ExecutionsFailed` | Step Functions metrics | End-to-end success rate |
| `ActivityTaskSuccess` / `ActivityTaskTimedOut` | Step Functions metrics | HITL response rate |
| `Invocations` on bus rules | EventBridge metrics | Event delivery count |

---

## Cost Estimation

Everything is pay-per-use. An idle stack costs **$0**.

| Component | Pricing |
|---|---|
| **Bedrock** | Nova Lite: ~$0.00008/1K input tokens, ~0.00032/1K output tokens. A full demo run uses ~5K tokens ≈ **$0.002**. |
| **Lambda** | 128–512 MB, ~2–5 s per call. ~$0.000002 per invocation. 7 calls ≈ **$0.00001**. |
| **Step Functions** | STANDARD: $0.025 per 1,000 state transitions. A full flow ≈ 10 transitions ≈ **$0.00025**. |
| **EventBridge** | $1.00 per 1M custom events. 4 events ≈ **$0.000004**. |
| **CloudWatch Logs** | ~$0.50/GB ingested. Each run ≈ 100 KB ≈ **$0.00005**. |

**Total per full demo run**: well under **$0.01**.

Note: `WaitForHuman` executions bill while paused (STANDARD execution type,
up to 1 hour). Always approve or reject HITL tasks rather than walking away.

---

## Security Considerations

- **IAM roles are shared**, not per-function — least-privilege where
  possible, but the choreography agents share an EventBridge `PutEvents`
  policy and the orchestration agents share Bedrock invoke permissions.
- **Bedrock access** is scoped to the specific model ARNs (inference profile
  and foundation model) — not `*`.
- **No secrets in code** — model id and bus name are environment variables
  injected by CloudFormation.
- **Lambda functions** run with the AWS-managed `AWSLambdaBasicExecutionRole`
  (CloudWatch Logs) and `AWSXRayDaemonWriteAccess` (tracing).
- **Step Functions** has only `SendTaskSuccess`/`SendTaskFailure` permissions
  (scoped to `*` — can be tightened per-ARN if needed).
- **EventBridge rules** target Lambdas via a dedicated `BusToLambdaRole` with
  `lambda:InvokeFunction` only on the four target ARNs.
- The deployment zip **excludes** `boto3`/`botocore`/`s3transfer` to avoid
  version drift with the Lambda runtime's copies.

### Recommendations for production

- Enable **CloudTrail** for full API audit logging.
- Add a **WAF** in front of any public API that triggers the flow.
- Use **Lambda reserved concurrency** to cap Bedrock spend.
- Store booking data in **DynamoDB** instead of logging to CloudWatch.
- Add **dead-letter queues** on Lambda for failed invocations.
- Use **AWS Config** rules to enforce model-id constraints.

---

## Troubleshooting

### `StateMachineDoesNotExist` when starting execution

```bash
aws stepfunctions list-state-machines --region us-east-1 \
  --query "stateMachines[?contains(name,'travel')].{name:name,arn:stateMachineArn}"
```

Use the ARN, not the name, or ensure the name matches exactly.

### `AccessDenied` on Bedrock

The role needs **both** `bedrock:InvokeModel` **and**
`bedrock:InvokeModelWithResponseStream` (Strands uses `ConverseStream`).
Check:

```bash
aws iam list-attached-role-policies --role-name OrchAgentRole --region us-east-1
```

### `us.amazon.nova-lite-v1:0` fails silently

The `us.` prefix is a **cross-region inference profile** that routes to
us-west-2. Your IAM policies are pinned to us-east-1. Use
`amazon.nova-lite-v1:0` (no `us.` prefix).

### Event chain stops after PlannerAgent

Check that rules use **different sources**:
- External trigger: `source: [travel.demo]`
- Agent events: `source: [travel.agents]`

If you copy-paste one pattern, the chain breaks.

### Lambda handler not found

Ensure the handler matches the file path inside the zip:
- `choreography.planner_handler.handler` → `src/choreography/planner_handler.py`
- `orch.planner.handler` → `src/orch/planner.py`

### `ValidationError: extraneous key [Type]`

Remove `Type: STANDARD` from the StateMachine properties — CloudFormation
does not accept it. The default type is STANDARD.

### Build fails with `ModuleNotFoundError: requests`

The build script installs `requests` automatically. If building manually:

```bash
pip install strands-agents==1.54.0 requests --target pkg/
```

---

## The Bug We Fixed in the Workshop ASL

The workshop's terminal `BookingSuccess` read
`$.plannerResult.booking_confirmation` — which is `null` on the
human-review path (the confirmation is only minted later, by
`PlannerFinalizeBooking`, in `$.finalBookingResult`). Execution #2
"succeeded" but returned `booking_confirmation: null`.

**Fix**: `PlannerFinalizeBooking` now ends in a dedicated
`BookingSuccessAfterReview` state that reads
`$.finalBookingResult.booking_confirmation`. The fixed ASL is in
[`asl/travel-booking-orchestration.json`](asl/travel-booking-orchestration.json)
and baked into the CloudFormation template.

---

## Differences from the Original Workshop

| Aspect | Workshop | This repo |
|---|---|---|
| Templates | SAM per module | **One CloudFormation template** for both modules |
| IAM roles | One per function | Shared (3 choreography, 3 orchestration, 1 bus, 1 SFN) |
| Module 2 agents | Not included (only sequential) | **Full parallel + HITL** (`src/orch/`) |
| Lambda names | Long workshop prefix | Short (`orch-*-agent`, `PlannerAgent`, etc.) |
| X-Ray tracing | Missing permissions | `AWSXRayDaemonWriteAccess` added |
| ASL bug | `BookingSuccessAfterReview` missing | **Fixed** and verified |
| Build | Manual per function | **Single `build-deployment-package.sh`** |
| HITL | SQS-based (workshop) | **Pure task-token pattern** (no SQS) |

---

## Repo Layout

```
agentic-ai-aws-serverless/
├── templates/
│   └── travel-agents.template.yml    # CloudFormation (both modules, validated)
├── asl/
│   └── travel-booking-orchestration.json  # Fixed ASL (for console copy-paste / SDK)
├── src/
│   ├── agents/                       # Shared agent brains
│   │   ├── planner.py                #   free-text → structured itinerary
│   │   ├── weather.py                #   forecast + advisory (deterministic gate)
│   │   ├── flight.py                 #   search + book (mock provider)
│   │   └── telemetry.py              #   OpenTelemetry init (Strands spans)
│   ├── choreography/                 # Module 1 handlers (event-driven)
│   │   ├── events.py                 #   emit() helper for EventBridge
│   │   ├── planner_handler.py        #   TripRequested → ItineraryPlanned
│   │   ├── weather_handler.py        #   ItineraryPlanned → WeatherChecked
│   │   ├── flight_handler.py         #   WeatherChecked → FlightBooked|TripAbandoned
│   │   └── collector_handler.py      #   terminal listener (logs outcome)
│   ├── orch/                         # Module 2 handlers (input in, result out)
│   │   ├── planner.py                #   extract | analyze_and_decide | finalize_booking
│   │   ├── weather.py                #   analyze (parallel branch)
│   │   └── flight.py                 #   search (parallel branch)
│   └── requirements.txt              # strands-agents + requests
├── scripts/
│   ├── build-deployment-package.sh   # builds combined zip (~12 MB)
│   ├── send_trip_request.py          # Module 1 trigger
│   ├── start_execution.py            # Module 2 start
│   ├── approve_task.py               # HITL worker (get_activity_task + send_task_success)
│   ├── sample-execution-auto.json    # budget=400 → auto-book
│   └── sample-execution-human.json   # budget=50 → human review
├── LICENSE                           # MIT (anuagarwaluk)
├── README.md
└── .gitignore
```

---

## Cleanup

Delete the stack and all resources:

```bash
aws cloudformation delete-stack --region us-east-1 --stack-name travel-agents
aws cloudformation wait stack-delete-complete --stack-name travel-agents --region us-east-1
```

Delete the code bucket (if you created it):

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 rb s3://travel-agents-code-${ACCOUNT_ID} --force
```

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Commit with clear messages
4. Open a PR against `main`

### Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt boto3
```

### Running tests

```bash
# Local unit tests (if added)
python3 -m pytest tests/ -v

# Build and smoke-test
scripts/build-deployment-package.sh
cd /tmp && unzip -t ~/agentic-ai-aws-serverless/travel-agents.zip
```

---

## License

MIT — see [LICENSE](LICENSE).

Original workshop material copyright (c) 2026 anuagarwaluk.
Module 2 orchestration handlers (`src/orch/`) and CloudFormation template
are original work.

---

## Authors

- **wazaglo** — Module 2 agents, CFN template, bug fix, deployment scripts
- **anuagarwaluk** — Original workshop (Module 1 choreography pattern, base agents)

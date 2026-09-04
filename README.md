# Agentic AI Architectures with AWS Serverless

Two multi-agent travel-booking systems — **choreography** and **orchestration** —
deployed from **one CloudFormation stack** to your own AWS account, both calling
Amazon Bedrock Nova Lite via the [Strands Agents SDK](https://strandsagents.com).

| | Module 1 — Choreography | Module 2 — Orchestration |
|---|---|---|
| Coordination | Domain events on a custom EventBridge bus; nobody calls anybody | A Step Functions state machine is the single source of truth |
| Agents | 4 Lambdas (planner, weather, flight, collector) | 3 Lambdas (planner, weather, flight-manager) |
| Branching | Hidden inside `flight_handler.py` | Visible `Choice` state |
| Parallelism | None (chain of events) | `Parallel`: weather + flight at the same time |
| Human-in-the-loop | — | Step Functions **Activity** + task tokens |

Based on the MIT-licensed AWS workshop
[anuagarwaluk/Agentic-AI-architectures-with-AWS-Serverless](https://github.com/anuagarwaluk/Agentic-AI-architectures-with-AWS-Serverless),
rebuilt in our own account. Added here: the Module 2 agents (`src/orch/`), a
**state-machine bug fix**, one combined CFN template, and production helper scripts.

## Architecture

### Module 1 — Choreography

![Module 1 choreography architecture](docs/images/architecture-choreography.svg)

Agents never call each other — they announce domain events on
`travel-agents-bus` and the next agent reacts. Three Lambdas call Bedrock.

### Module 2 — Orchestration

![Module 2 orchestration architecture](docs/images/architecture-orchestration.svg)

The budget gate is **deterministic code** (auditable, reproducible); the LLM
only writes traveller-facing prose. Every path ends in a terminal state.

### Deployed and verified

Evidence from the live stack (us-east-1), captured via an STS-federated console session:

| | |
|---|---|
| ![CloudFormation](docs/screenshots/01-cloudformation-stack.png) | **CloudFormation** — all resources `CREATE_COMPLETE` |
| ![Execution](docs/screenshots/03-sfn-execution-success.png) | **Step Functions** — execution `SUCCEEDED`, booking confirmed |
| ![Lambda](docs/screenshots/02-lambda-functions.png) | **Lambda** — 7 agent functions |
| ![EventBridge](docs/screenshots/06-eventbridge-bus.png) | **EventBridge** — `travel-agents-bus` + 4 rules |

More: [state machine](docs/screenshots/04-sfn-state-machine.png) ·
[activity](docs/screenshots/05-sfn-activity.png) ·
[business rules](docs/screenshots/07-eventbridge-rules.png) ·
[DLQ](docs/screenshots/08-sqs-dead-letter-queue.png) ·
[S3 code](docs/screenshots/09-s3-code-bucket.png) ·
[log groups](docs/screenshots/10-cloudwatch-log-groups.png) ·
[SFN logs](docs/screenshots/11-cloudwatch-sfn-logs.png)

## Prerequisites

- AWS account, `us-east-1`, AWS CLI v2 + `boto3` + `zip`
- Bedrock model access for `amazon.nova-lite-v1:0` in us-east-1
  (Console → Bedrock → Model access)

## Deploy

```bash
# 1. build the combined zip (strands-agents bundled; boto3 excluded — runtime provides it)
scripts/build-deployment-package.sh

# 2. upload
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb s3://travel-agents-code-${ACCOUNT_ID} --region us-east-1 2>/dev/null || true
aws s3 cp travel-agents.zip s3://travel-agents-code-${ACCOUNT_ID}/travel-agents.zip

# 3. one stack for everything
aws cloudformation deploy \
  --region us-east-1 --stack-name travel-agents \
  --template-file templates/travel-agents.template.yml \
  --parameter-overrides CodeBucket=travel-agents-code-${ACCOUNT_ID} \
  --capabilities CAPABILITY_NAMED_IAM
```

Creates: custom bus + 4 rules, 7 Lambdas, the `travel-booking-orchestration`
state machine, the `human-review` activity, 5 IAM roles, an SQS dead-letter
queue, and CloudWatch log groups with retention. Parameters
(`CodeBucket`, `ModelId`, `BusName`, `ActivityName`, `LogRetentionDays`) — see
[templates/README.md](templates/README.md).

## Run the demos

**Module 1** — fire a request, watch the chain:

```bash
aws logs tail /aws/lambda/TripCollector --follow --region us-east-1   # terminal 1
python3 scripts/send_trip_request.py "3 days in Lisbon in May from London"  # terminal 2
```

Planner → Weather → Flight → Collector: four decoupled LLM invocations;
the collector logs `=== TRIP FlightBooked ===` (or `TripAbandoned` when the
rain probability exceeds 60%).

**Module 2** — auto-book, or pause for a human:

```bash
python3 scripts/start_execution.py --input-file scripts/sample-execution-auto.json   # budget 400 -> books

python3 scripts/start_execution.py --input-file scripts/sample-execution-human.json  # budget 50  -> pauses
python3 scripts/approve_task.py --decision approved                                  # resumes, finalizes
```

The `budget` field is the gate: `>= 100` books, `< 100` waits in
`WaitForHuman` until `approve_task.py` resolves the task token. Input schema
and more flags: [scripts/README.md](scripts/README.md).

## The bug we fixed

The workshop's terminal `BookingSuccess` read
`$.plannerResult.booking_confirmation` — `null` on the human-review path
(the confirmation is minted later by `PlannerFinalizeBooking`). We added a
dedicated `BookingSuccessAfterReview` terminal state reading
`$.finalBookingResult.booking_confirmation`. Fixed ASL:
[asl/travel-booking-orchestration.json](asl/travel-booking-orchestration.json).

## Repo layout

- [templates/](templates/README.md) — the whole stack in one CFN template
- [src/](src/README.md) — Lambda code: [agents/](src/agents/README.md) (shared brains),
  [choreography/](src/choreography/README.md) (Module 1), [orch/](src/orch/README.md) (Module 2)
- [scripts/](scripts/README.md) — build + demo helpers
- [asl/](asl/README.md) — raw state machine definition (with the bug fix)
- [docs/](docs/README.md) — diagrams, console screenshots, operations guide

## Operations

Monitoring, X-Ray, cost breakdown, security notes and troubleshooting:
**[docs/operations.md](docs/operations.md)**.

## Cleanup

```bash
aws cloudformation delete-stack --region us-east-1 --stack-name travel-agents
aws s3 rb s3://travel-agents-code-${ACCOUNT_ID} --force
```

## License

MIT — see [LICENSE](LICENSE). Workshop material © 2026 anuagarwaluk.

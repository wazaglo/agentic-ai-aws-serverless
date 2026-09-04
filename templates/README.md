# `templates/` — CloudFormation

`travel-agents.template.yml` — the **whole system in one stack**: both demo
modules, all IAM, logging and the dead-letter queue. Written so you can tear
it down and rebuild the account state in one command.

## What it creates

| Group | Resources |
|---|---|
| Module 1 | `travel-agents-bus` (EventBridge), 4 rules (`travel-on-*`), `PlannerAgent`, `WeatherAgent`, `FlightAgent`, `TripCollector`, `BusToLambdaRole`, `AgentRole`, `CollectorRole` |
| Module 2 | `human-review` Activity, `travel-booking-orchestration` state machine (ASL inlined as native YAML), `orch-planner-agent`, `orch-weather-agent`, `orch-flight-manager-agent`, `OrchAgentRole`, `StepFunctionsExecutionRole` |
| Observability | 8 CloudWatch log groups with `LogRetentionDays` retention, X-Ray active tracing everywhere, SFN `ALL`-level execution logging |
| Safety | SQS dead-letter queue wired into every agent Lambda, `DeletionPolicy: Delete` on the state machine |

## Parameters

| Parameter | Default | Notes |
|---|---|---|
| `CodeBucket` | *(required)* | bucket containing the built zip — upload first |
| `CodeKey` | `travel-agents.zip` | |
| `ModelId` | `amazon.nova-lite-v1:0` | **not** `us.amazon...` (cross-region trap) |
| `BusName` | `travel-agents-bus` | |
| `ActivityName` | `human-review` | |
| `LogRetentionDays` | `30` | validated enum of CloudWatch values |

## Deploy / update / delete

```bash
# deploy (requires CAPABILITY_NAMED_IAM — the stack creates named roles)
aws cloudformation deploy --region us-east-1 --stack-name travel-agents \
  --template-file templates/travel-agents.template.yml \
  --parameter-overrides CodeBucket=my-bucket CodeKey=travel-agents.zip \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation delete-stack --region us-east-1 --stack-name travel-agents
```

## Hard-won template lessons

- `AWS::StepFunctions::StateMachine` `Definition` must be **native YAML/JSON**,
  not a `!Sub` string. Use `!GetAtt` for Lambda ARNs and `!Sub` only for the
  activity ARN.
- There is **no `Type: STANDARD` property** — adding it fails model validation.
- `TracingConfiguration` takes `Enabled: true`; `Mode: PassThrough` is SDK-only.
- The name property is `StateMachineName`, not `Name`.
- `events:PutEvents` needs the bus **ARN** (`!GetAtt TravelBus.Arn`), not the name.

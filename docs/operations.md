# Operations

## Monitoring

- **CloudWatch Logs**: each Lambda writes to `/aws/lambda/<FunctionName>`:
  `aws logs tail /aws/lambda/orch-planner-agent --follow --region us-east-1`
- **State machine logs**: every execution event at `ALL` level lands in
  `/aws/vendedlogs/states/travel-booking-orchestration`.
- **X-Ray**: active tracing on all Lambdas + the state machine; traces show
  Bedrock latency and Strands spans.
- **Strands telemetry**: OpenTelemetry spans via console exporter; set
  `OTEL_EXPORTER_OTLP_ENDPOINT` (ADOT layer) for real traces.
- **Dead-letter queue**: `travel-agents-dead-letter` (SQS, 14-day retention)
  captures failed Lambda invocations.

Key metrics: Lambda `Invocations`/`Errors`/`Duration`; SFN
`ExecutionsSucceeded/Failed/Aborted`, `ActivityTaskTimedOut`; EventBridge
`Invocations` per rule.

## Cost

Idle stack: **$0**. Per full demo run (all pay-per-use):

| Component | Cost |
|---|---|
| Bedrock Nova Lite (~5K tokens) | ~$0.002 |
| Lambda (7 calls, 512 MB, few seconds) | ~$0.00001 |
| Step Functions (~10 transitions) | ~$0.00025 |
| EventBridge (4 events) | negligible |
| CloudWatch Logs (~100 KB) | negligible |

Caution: `WaitForHuman` executions **bill while paused** (up to 1 h). Approve
or reject, don't walk away.

## Security

- Bedrock IAM scoped to the specific foundation-model + inference-profile ARNs.
- Strands uses `ConverseStream` → roles need `bedrock:InvokeModelWithResponseStream`,
  not just `InvokeModel`.
- EventBridge rules invoke Lambdas via a dedicated role scoped to the 4 target ARNs.
- SFN execution role: Lambda invoke on the 3 orch functions + task-token
  send + the 10 log-delivery actions.
- No secrets in code; config via environment variables from the template.
- Deployment zip excludes `boto3`/`botocore`/`s3transfer` (runtime copies win).
- Production hardening ideas: CloudTrail, reserved Lambda concurrency (caps
  Bedrock spend), DynamoDB for booking data, WAF in front of any trigger API.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `StateMachineDoesNotExist` | List SMs and use the exact name/ARN: `aws stepfunctions list-state-machines` |
| `AccessDenied` on Bedrock | Role needs `InvokeModelWithResponseStream` on model + profile ARNs |
| Silent cross-region failure | Don't use `us.amazon.nova-lite-v1:0` - it routes to us-west-2; use `amazon.nova-lite-v1:0` |
| Chain stops after PlannerAgent | Rule sources differ on purpose: external `travel.demo`, agents `travel.agents` |
| `Handler ... not found` | Handler path must match zip layout: `orch.planner.handler`, `choreography.planner_handler.handler` |
| CFN: `extraneous key [Type]` | `Type: STANDARD` is not a valid CFN property; default is STANDARD |
| CFN: Definition "expected JSONObject, found String" | Use native YAML Definition with `!GetAtt`, not `!Sub` |
| CFN: `does not have permissions to call SendMessage on SQS` | Lambda update must wait for the DLQ policy → `DependsOn: DeadLetterQueuePolicy` |
| SFN: `not authorized to access the Log Destination` | The 10 log-delivery actions must be granted with `Resource: "*"` (these actions don't support resource-level scoping) |

## Differences from the original workshop

| Aspect | Workshop | This repo |
|---|---|---|
| Templates | SAM per module | One CFN template, both modules |
| Module 2 | Sequential only | Parallel + HITL (`src/orch/`) |
| HITL | SQS-based | Pure task-token Activity |
| ASL bug | `BookingSuccessAfterReview` missing | Fixed |
| DLQ / log retention / SFN logs | None | In the stack |

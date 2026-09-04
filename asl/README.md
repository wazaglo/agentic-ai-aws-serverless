# `asl/` — raw state machine definition

`travel-booking-orchestration.json` — the Amazon States Language definition of
the Module 2 state machine, **with the bug fix** described in the top-level
README. This copy exists for people who want to create or update the state
machine from the Step Functions console or the SDK instead of CloudFormation.

> The CloudFormation template inlines the same ASL as native YAML. Keep the
> two in sync if you edit either one.

## Structure

```
PlannerExtract → Parallel[WeatherGet | FlightSearch] → PlannerAnalyzeAndBook
  → CheckPlannerDecision (Choice on $.plannerResult.decision)
      booked              → BookingSuccess
      needs_human_review  → WaitForHuman (activity, 1 h)
            approved      → PlannerFinalizeBooking → BookingSuccessAfterReview
            rejected      → BookingRejected
            timeout       → HumanReviewTimeout
      (anything else)     → HandleError
```

- Every Task state **retries** transient Lambda errors 3× with exponential
  backoff and **catches** `States.ALL` into `HandleError`, so executions
  always reach a terminal state with a JSON result.
- `WaitForHuman` is a plain Activity task (pure task-token pattern — no SQS).
  Resolve it from anywhere with `states:SendTaskSuccess`.
- `BookingSuccess` vs `BookingSuccessAfterReview` is **the fix**: the two
  terminal paths read `booking_confirmation` from different JSONPaths
  (`$.plannerResult` vs `$.finalBookingResult`). The original workshop read
  the wrong path on the human-review path and returned `null`.

## Before using this file directly

The `FunctionName` and `Resource` (activity) ARNs point at the **original
workshop account**. Replace them with your own ARNs (or use the CFN template,
which resolves them via `!GetAtt`), then:

```bash
aws stepfunctions update-state-machine \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:travel-booking-orchestration \
  --definition "file://asl/travel-booking-orchestration.json"
```

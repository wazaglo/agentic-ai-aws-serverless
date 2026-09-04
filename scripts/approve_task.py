"""Module 2 (HITL): the human-approver worker for the `human-review` activity.

Long-polls the Step Functions Activity, shows the pending decision, then
completes the task with your verdict. The state machine resumes in
ProcessHumanDecision: approved -> PlannerFinalizeBooking ->
BookingSuccessAfterReview; rejected -> BookingRejected.

This is also a tiny demo of the "human as a worker" pattern: the SM waits on a
task token, and ANY client with states:SendTaskSuccess can resolve it.

Usage:
  python scripts/approve_task.py --decision approved
  python scripts/approve_task.py --decision rejected --reason "too risky"
  python scripts/approve_task.py --decision approved --dry-run   # just look
"""
import argparse
import json

import boto3

parser = argparse.ArgumentParser()
parser.add_argument("--activity-name", default="human-review")
parser.add_argument("--decision", choices=["approved", "rejected"], default="approved")
parser.add_argument("--reason", default="looks good")
parser.add_argument("--worker", default="reviewer-cli")
parser.add_argument("--dry-run", action="store_true",
                    help="fetch and show the task but do NOT resolve it")
args = parser.parse_args()

sfn = boto3.client("stepfunctions")
acct = boto3.client("sts").get_caller_identity()["Account"]
region = sfn.meta.region_name
activity_arn = f"arn:aws:states:{region}:{acct}:activity:{args.activity_name}"

task = sfn.get_activity_task(activityArn=activity_arn, workerName=args.worker)
if "taskToken" not in task:
    raise SystemExit("No pending human-review tasks right now.")

print("Pending decision:")
print(json.dumps(json.loads(task["input"]), indent=2)[:2000])
print(f"\ntaskToken: {task['taskToken'][:60]}...")

if args.dry_run:
    raise SystemExit("--dry-run: task left pending (re-poll later to resolve).")

sfn.send_task_success(
    taskToken=task["taskToken"],
    output=json.dumps({"decision": args.decision, "reason": args.reason,
                       "reviewer": args.worker}),
)
print(f"Sent {args.decision} -> execution continues in ProcessHumanDecision.")

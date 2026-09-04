"""Module 2 (orchestration): start one travel-booking execution.

The state machine expects the structured booking input (see the JSON files in
this directory). `budget` is the deterministic gate in the planner handler:
  budget >= 100  -> planner books automatically (no human touch)
  budget <  100  -> needs_human_review -> the run pauses in WaitForHuman
                     until scripts/approve_task.py completes the activity task.

Usage:
  python scripts/start_execution.py --input-file scripts/sample-execution-auto.json
  python scripts/start_execution.py --input-file scripts/sample-execution-human.json
"""
import argparse
import json
import uuid

import boto3

parser = argparse.ArgumentParser()
parser.add_argument("--input-file", required=True)
parser.add_argument("--state-machine-name", default="travel-booking-orchestration")
args = parser.parse_args()

with open(args.input_file) as f:
    payload = json.load(f)

sfn = boto3.client("stepfunctions")
sm_arn = next(
    sm["stateMachineArn"]
    for sm in sfn.list_state_machines()["stateMachines"]
    if sm["name"] == args.state_machine_name
)
execution = sfn.start_execution(
    stateMachineArn=sm_arn,
    name=str(uuid.uuid4()),
    input=json.dumps(payload),
)
region = sm_arn.split(":")[3]
print(f"Execution started: {execution['executionArn']}")
print("Console: https://{r}.console.aws.amazon.com/states/home?region={r}"
      "#/v2/executions/details/{e}".format(r=region, e=execution["executionArn"]))
if payload.get("budget", 1000) < 100:
    print("budget < 100 -> the run will pause in WaitForHuman.")
    print("Approve it:  python scripts/approve_task.py --decision approved")

"""Module 2 (orchestration): start one travel-booking execution.

The state machine expects the structured booking input (see the JSON files in
this directory). `budget` is the deterministic gate in the planner handler:
  budget >= 100  -> planner books automatically (no human touch)
  budget <  100  -> needs_human_review -> the run pauses in WaitForHuman
                     until scripts/approve_task.py completes the activity task.

Usage:
  python3 scripts/start_execution.py --input-file scripts/sample-execution-auto.json
  python3 scripts/start_execution.py --input-file scripts/sample-execution-human.json
"""
import argparse
import json
import sys
import uuid

import boto3


def main():
    parser = argparse.ArgumentParser(description="Start a Step Functions execution for Module 2")
    parser.add_argument("--input-file", required=True, help="path to JSON input file")
    parser.add_argument("--state-machine-name", default="travel-booking-orchestration")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--json", action="store_true", help="output JSON instead of text")
    args = parser.parse_args()

    try:
        with open(args.input_file) as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read input file: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        sfn = boto3.client("stepfunctions", region_name=args.region)
        sm_arn = next(
            sm["stateMachineArn"]
            for sm in sfn.list_state_machines()["stateMachines"]
            if sm["name"] == args.state_machine_name
        )
    except StopIteration:
        print(f"ERROR: state machine '{args.state_machine_name}' not found in {args.region}", file=sys.stderr)
        sys.exit(1)

    try:
        execution = sfn.start_execution(
            stateMachineArn=sm_arn,
            name=str(uuid.uuid4()),
            input=json.dumps(payload),
        )
    except Exception as exc:
        print(f"ERROR: start_execution failed: {exc}", file=sys.stderr)
        sys.exit(1)

    region = sm_arn.split(":")[3]
    console_url = (
        f"https://{region}.console.aws.amazon.com/states/home"
        f"?region={region}#/v2/executions/details/{execution['executionArn']}"
    )

    if args.json:
        print(json.dumps({
            "executionArn": execution["executionArn"],
            "consoleUrl": console_url,
            "budget": payload.get("budget"),
        }))
    else:
        print(f"Execution started: {execution['executionArn']}")
        print(f"Console: {console_url}")
        if payload.get("budget", 1000) < 100:
            print("budget < 100 -> the run will pause in WaitForHuman.")
            print("Approve it:  python3 scripts/approve_task.py --decision approved")


if __name__ == "__main__":
    main()

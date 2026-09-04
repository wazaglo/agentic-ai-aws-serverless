"""Module 1 (choreography): kick off the flow with a TripRequested event.

The rule travel-on-trip-requested matches source `travel.demo` on the custom
bus; downstream events are emitted by the agents themselves under source
`travel.agents`.

Usage:
  python3 scripts/send_trip_request.py "3 days in Lisbon in May from London"

Watch it land:
  aws logs tail /aws/lambda/TripCollector --follow --region us-east-1
"""
import argparse
import json
import sys

import boto3


def main():
    parser = argparse.ArgumentParser(description="Send a TripRequested event to trigger Module 1")
    parser.add_argument("request", help="natural language trip request")
    parser.add_argument("--bus", default="travel-agents-bus", help="EventBridge bus name")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    try:
        events = boto3.client("events", region_name=args.region)
        resp = events.put_events(Entries=[{
            "Source": "travel.demo",
            "DetailType": "TripRequested",
            "Detail": json.dumps({"request": args.request}),
            "EventBusName": args.bus,
        }])
        entry = resp["Entries"][0]
        if "ErrorCode" in entry:
            print(f"ERROR: put_events failed: {entry}", file=sys.stderr)
            sys.exit(1)
        print(f"TripRequested sent (event id {entry['EventId']}).")
        print("Follow the chain: PlannerAgent -> WeatherAgent -> FlightAgent -> TripCollector")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

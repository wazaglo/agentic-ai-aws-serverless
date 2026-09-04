"""Module 1 (choreography): kick off the flow with a TripRequested event.

The rule travel-on-trip-requested matches source `travel.demo` on the custom
bus; downstream events are emitted by the agents themselves under source
`travel.agents`.

Usage:
  python scripts/send_trip_request.py "3 days in Lisbon in May from London"

Watch it land:
  aws logs tail /aws/lambda/TripCollector --follow --region us-east-1
"""
import argparse
import json

import boto3

parser = argparse.ArgumentParser()
parser.add_argument("request", help="natural language trip request")
parser.add_argument("--bus", default="travel-agents-bus")
args = parser.parse_args()

resp = boto3.client("events").put_events(Entries=[{
    "Source": "travel.demo",
    "DetailType": "TripRequested",
    "Detail": json.dumps({"request": args.request}),
    "EventBusName": args.bus,
}])
entry = resp["Entries"][0]
if "ErrorCode" in entry:
    raise SystemExit(f"put_events failed: {entry}")
print(f"TripRequested sent (event id {entry['EventId']}).")
print("Follow the chain: PlannerAgent -> WeatherAgent -> FlightAgent -> TripCollector logs.")

"""Tiny helper for emitting domain events. In choreography, this is the
only way agents talk: they announce what happened, they never call each
other."""
import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

_events = boto3.client("events")
BUS = os.environ.get("EVENT_BUS_NAME", "travel-agents-bus")


def emit(detail_type: str, detail: dict) -> None:
    """Emit a domain event on the custom EventBridge bus."""
    _events.put_events(Entries=[{
        "Source": "travel.agents",
        "DetailType": detail_type,
        "Detail": json.dumps(detail, default=str),
        "EventBusName": BUS,
    }])
    logger.info("emitted %s on %s", detail_type, BUS)

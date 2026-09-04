"""Choreography step 1. Reacts to TripRequested, announces ItineraryPlanned.
Knows nothing about the weather or flight agents."""
import json
import logging

from agents.planner import plan_trip
from choreography.events import emit

logger = logging.getLogger(__name__)


def handler(event, _context):
    logger.info("received event: %s", json.dumps(event.get("detail", {}), default=str)[:500])
    try:
        request = event["detail"]["request"]
        itinerary = plan_trip(request)
        emit("ItineraryPlanned", {"itinerary": itinerary})
        return {"ok": True}
    except Exception as exc:
        logger.error("planner_handler failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}

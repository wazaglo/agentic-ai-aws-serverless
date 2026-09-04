"""Choreography step 1. Reacts to TripRequested, announces ItineraryPlanned.
Knows nothing about the weather or flight agents."""
from agents.planner import plan_trip
from choreography.events import emit


def handler(event, _context):
    request = event["detail"]["request"]
    itinerary = plan_trip(request)
    emit("ItineraryPlanned", {"itinerary": itinerary})
    return {"ok": True}

"""Choreography step 3. Reacts to WeatherChecked. Books when the advisory
says PROCEED, otherwise announces the trip was abandoned. The branch lives
inside the agent's handler here; in the orchestration pattern the same
branch is a visible Choice state owned by the state machine."""
import json
import logging

from agents.flight import book_trip_flight
from choreography.events import emit

logger = logging.getLogger(__name__)


def handler(event, _context):
    logger.info("received event: %s", json.dumps(event.get("detail", {}), default=str)[:500])
    try:
        detail = event["detail"]
        itinerary, weather = detail["itinerary"], detail["weather"]

        if weather["advisory"] != "PROCEED":
            logger.info("advisory=%s, abandoning trip", weather["advisory"])
            emit("TripAbandoned", {"itinerary": itinerary, "weather": weather,
                                   "reason": "weather advisory"})
            return {"ok": True, "booked": False}

        booking = book_trip_flight(itinerary, weather)
        emit("FlightBooked", {"itinerary": itinerary, "weather": weather,
                              "booking": booking})
        return {"ok": True, "booked": True}
    except Exception as exc:
        logger.error("flight_handler failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}

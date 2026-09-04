"""Choreography step 2. Reacts to ItineraryPlanned, announces WeatherChecked."""
import json
import logging

from agents.weather import check_weather
from choreography.events import emit

logger = logging.getLogger(__name__)


def handler(event, _context):
    logger.info("received event: %s", json.dumps(event.get("detail", {}), default=str)[:500])
    try:
        itinerary = event["detail"]["itinerary"]
        weather = check_weather(itinerary)
        emit("WeatherChecked", {"itinerary": itinerary, "weather": weather})
        return {"ok": True}
    except Exception as exc:
        logger.error("weather_handler failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}

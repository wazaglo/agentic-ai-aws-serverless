"""Choreography step 2. Reacts to ItineraryPlanned, announces WeatherChecked."""
from agents.weather import check_weather
from choreography.events import emit


def handler(event, _context):
    itinerary = event["detail"]["itinerary"]
    weather = check_weather(itinerary)
    emit("WeatherChecked", {"itinerary": itinerary, "weather": weather})
    return {"ok": True}

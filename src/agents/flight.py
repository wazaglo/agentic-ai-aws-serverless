"""Flight booking agent: searches options and books one.

The flight provider is a deterministic mock so the workshop costs nothing
and never books a real seat. Swap the two tools for a GDS or partner API
and nothing else in either pattern changes. That is the point.
"""
import hashlib
import logging
import os

from strands import Agent, tool
from strands.models import BedrockModel

from agents.telemetry import init_telemetry

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


@tool
def search_flights(origin: str, destination: str, depart_date: str) -> list:
    """Return available flights for a route and date, cheapest first.
    Mock provider: deterministic results derived from the route and date."""
    if not all([origin, destination, depart_date]):
        logger.warning("search_flights called with empty args: %s %s %s", origin, destination, depart_date)
        return []
    s = _seed(origin, destination, depart_date)
    carriers = ["Skyline", "Atlas Air", "Meridian"]
    return sorted(
        [
            {
                "flight_no": f"{carriers[i][:2].upper()}{100 + (s >> i) % 800}",
                "carrier": carriers[i],
                "depart": f"{6 + (s >> (i + 3)) % 14:02d}:{(s >> i) % 6}0",
                "price_gbp": 79 + (s >> (i + 5)) % 240,
                "direct": bool((s >> (i + 7)) % 2),
            }
            for i in range(3)
        ],
        key=lambda f: f["price_gbp"],
    )


@tool
def book_flight(flight_no: str, passenger_note: str) -> dict:
    """Book a flight by flight number. Mock provider: always confirms and
    returns a deterministic confirmation code."""
    if not flight_no:
        raise ValueError("flight_no is required")
    code = hashlib.sha256(flight_no.encode()).hexdigest()[:6].upper()
    confirmation = f"TRV-{code}"
    logger.info("booked flight %s -> %s", flight_no, confirmation)
    return {"status": "CONFIRMED", "flight_no": flight_no,
            "confirmation": confirmation, "note": passenger_note}


_agent = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        init_telemetry("flight-agent")
        _agent = Agent(
            model=BedrockModel(model_id=MODEL_ID),
            system_prompt=("You are a flight booking agent. Search flights "
                           "with the tools, pick the best value sensible "
                           "option (prefer direct when close in price), book "
                           "it, and reply with one confirmation sentence "
                           "that includes the confirmation code."),
            tools=[search_flights, book_flight],
        )
    return _agent


def book_trip_flight(itinerary: dict, weather: dict) -> dict:
    """Let the agent choose and book a flight for the itinerary."""
    prompt = (
        f"Book a flight from {itinerary.get('origin', 'unknown')} to "
        f"{itinerary.get('destination', 'unknown')} departing "
        f"{itinerary.get('depart_date', 'unknown')}. "
        f"Weather advisory: {weather.get('advisory', 'unknown')}. "
        f"Traveller notes: {itinerary.get('traveller_notes', 'none')}."
    )
    try:
        confirmation_text = _get_agent()(prompt).message["content"][0]["text"]
    except Exception as exc:
        logger.error("flight LLM call failed: %s", exc)
        confirmation_text = f"Booking failed: {exc}"
    return {"status": "BOOKED", "confirmation_text": confirmation_text}

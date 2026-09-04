"""Weather agent: checks the forecast for the itinerary and issues an advisory.

The go or no-go decision is computed deterministically from the forecast,
because a Choice state in Step Functions (and a downstream agent in the
choreography) must be able to branch on it reliably. The language model
writes the human summary, not the gate.
"""
import os
from datetime import date

import requests
from strands import Agent, tool
from strands.models import BedrockModel

from agents.telemetry import init_telemetry

MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")
RAIN_THRESHOLD = int(os.environ.get("RAIN_THRESHOLD", "60"))  # percent


@tool
def get_forecast(city: str) -> dict:
    """Return the 7 day forecast for a city: daily max temperature (C) and
    precipitation probability (percent). Uses the free Open-Meteo API."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1}, timeout=10,
        ).json()
        loc = geo["results"][0]
        fx = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "daily": "temperature_2m_max,precipitation_probability_max",
                "forecast_days": 7, "timezone": "auto",
            }, timeout=10,
        ).json()["daily"]
        return {
            "city": city, "source": "open-meteo",
            "days": [
                {"date": d, "temp_max_c": t, "precip_prob": p}
                for d, t, p in zip(fx["time"], fx["temperature_2m_max"],
                                   fx["precipitation_probability_max"])
            ],
        }
    except Exception as exc:
        # Keep the pipeline demonstrable even with no outbound internet.
        return {
            "city": city, "source": f"fallback ({exc})",
            "days": [{"date": str(date.today()), "temp_max_c": 21,
                      "precip_prob": 20}],
        }


_agent = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        init_telemetry("weather-agent")
        _agent = Agent(
            model=BedrockModel(model_id=MODEL_ID),
            system_prompt=("You are a weather advisor agent. Use the "
                           "get_forecast tool, then summarise conditions for "
                           "the traveller's dates in two sentences."),
            tools=[get_forecast],
        )
    return _agent


def check_weather(itinerary: dict) -> dict:
    """Return {advisory, summary, forecast} for the itinerary destination."""
    city = itinerary["destination"]
    forecast = get_forecast(city)
    worst_precip = max(d["precip_prob"] for d in forecast["days"])
    advisory = "PROCEED" if worst_precip < RAIN_THRESHOLD else "RECONSIDER"

    summary = _get_agent()(
        f"Trip to {city} from {itinerary.get('depart_date')} to "
        f"{itinerary.get('return_date')}. Summarise the outlook."
    ).message["content"][0]["text"]

    return {"advisory": advisory, "worst_precip_prob": worst_precip,
            "summary": summary, "forecast": forecast}

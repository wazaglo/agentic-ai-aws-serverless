"""Orchestration v2: the weather agent as a pure task (action=analyze).

Returns exactly the shape the Parallel branch's ResultSelector reads:
{statusCode, weather_analysis, risk_level, conditions, recommendation}.
risk_level is deterministic code (an auditable gate); the model writes prose."""
import json
import logging
import os
import re

from strands import Agent
from strands.models import BedrockModel

from agents.telemetry import init_telemetry
from agents.weather import get_forecast

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")

_agent = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        init_telemetry("orch-weather-agent")
        _agent = Agent(
            model=BedrockModel(model_id=MODEL_ID),
            system_prompt=(
                "You are a weather advisor in a travel booking system. "
                "Given forecast data, write two fields: weather_analysis "
                "(two factual sentences for the traveller) and recommendation "
                "(one sentence). Reply with ONLY a JSON object, no prose and no "
                "markdown fences: {\"weather_analysis\": \"...\", \"recommendation\": \"...\"}"
            ),
        )
    return _agent


def _risk_level(worst_precip: float, fallback: bool) -> str:
    if fallback:
        return "MODERATE"
    if worst_precip < 40:
        return "LOW"
    if worst_precip < 60:
        return "MODERATE"
    return "HIGH"


def analyze(event: dict) -> dict:
    city = event.get("destination") or "unknown"
    forecast = get_forecast(city)
    days = forecast.get("days", [])
    worst = max((d.get("precip_prob", 0) for d in days), default=0)
    fallback = str(forecast.get("source", "")).startswith("fallback")
    risk = _risk_level(worst, fallback)

    try:
        text = _get_agent()(json.dumps(
            {"city": city, "travel_dates": event.get("travel_dates"), "days": days}
        )).message["content"][0]["text"]
        match = re.search(r"\{.*\}", text, re.DOTALL)
        pair = json.loads(match.group(0)) if match else {}
    except Exception as exc:
        logger.warning("orch-weather LLM failed: %s", exc)
        pair = {}

    if risk == "HIGH":
        default_rec = "High rain risk; review travel plans or consider rebooking."
    else:
        default_rec = "Conditions look fine for travel."

    logger.info("weather for %s: risk=%s worst=%d%%", city, risk, worst)
    return {
        "statusCode": 200,
        "weather_analysis": str(pair.get("weather_analysis") or
                                f"{city}: worst rain probability {worst}% over the forecast window."),
        "risk_level": risk,
        "conditions": days,
        "recommendation": str(pair.get("recommendation") or default_rec),
    }


def handler(event, _context):
    try:
        if event.get("action") != "analyze":
            return {"statusCode": 400, "error": f"unknown action: {event.get('action')}"}
        return analyze(event)
    except Exception as exc:
        logger.error("orch-weather handler failed: %s", exc, exc_info=True)
        return {"statusCode": 500, "error": str(exc)}

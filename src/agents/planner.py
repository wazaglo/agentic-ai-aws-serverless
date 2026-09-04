"""Planner agent: turns a free-text travel request into a structured itinerary."""
import json
import os
import re

from strands import Agent
from strands.models import BedrockModel

from agents.telemetry import init_telemetry

MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")

SYSTEM_PROMPT = """You are a travel planner agent in a multi-agent system.
Turn the user's request into a structured itinerary.
Respond with ONLY a JSON object, no prose and no markdown fences, using exactly:
{"origin": "...", "destination": "...", "depart_date": "YYYY-MM-DD",
 "return_date": "YYYY-MM-DD", "traveller_notes": "...",
 "activities": ["...", "..."]}
If dates are vague, choose sensible concrete dates in the near future."""

_agent = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        init_telemetry("planner-agent")
        _agent = Agent(model=BedrockModel(model_id=MODEL_ID),
                       system_prompt=SYSTEM_PROMPT)
    return _agent


def plan_trip(request: str) -> dict:
    """Return a structured itinerary for a natural language trip request."""
    text = _get_agent()(request).message["content"][0]["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"planner returned no JSON: {text[:200]}")
    itinerary = json.loads(match.group(0))
    itinerary["request"] = request
    return itinerary

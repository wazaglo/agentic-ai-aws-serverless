"""Orchestration v2: the planner agent as a multi-action task.

The state machine calls this ONE function three times, selecting the action:
  extract            -> normalise the request, propose activities
  analyze_and_decide -> deterministic booked / needs_human_review gate;
                        auto-books the mock flight when it says booked
  finalize_booking   -> book after a human approved via the Activity

The gate is deterministic code (auditable, like Module 1's weather gate);
the model writes the human-facing prose. On any model failure we degrade to
code-generated prose but keep the deterministic decision, and we always
return the consistent {statusCode, ...} structure so the ASL never crashes.
"""
import json
import logging
import os
import re

from strands import Agent
from strands.models import BedrockModel

from agents.flight import book_flight
from agents.telemetry import init_telemetry

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")

_agent = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        init_telemetry("orch-planner-agent")
        _agent = Agent(
            model=BedrockModel(model_id=MODEL_ID),
            system_prompt=(
                "You are a senior travel planner in a multi-agent booking "
                "system. You extract requests, analyse weather and flight "
                "data, and explain decisions. You never invent flights. "
                "Always reply with ONLY a JSON object, no prose and no "
                "markdown fences."
            ),
        )
    return _agent


def _model_json(prompt: str) -> dict:
    text = _get_agent()(prompt).message["content"][0]["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"model returned no JSON: {text[:200]}")
    return json.loads(match.group(0))


def extract(event: dict) -> dict:
    """Normalise the free-text request into structured data."""
    request = {k: event.get(k) for k in
               ("origin", "destination", "travel_dates", "travelers",
                "budget", "airline_preference", "interests")}
    fallback_data = {
        "origin": event.get("origin"),
        "destination": event.get("destination"),
        "travel_dates": event.get("travel_dates"),
        "travelers": event.get("travelers", 1),
        "budget": event.get("budget"),
        "activities": [],
        "summary": f"Trip {event.get('origin')} to {event.get('destination')}.",
    }
    confidence = 0.5
    try:
        data = _model_json(
            "Extract and normalise this travel request. Reply with ONLY JSON: "
            "{\"extractedData\": {\"origin\": \"...\", \"destination\": \"...\", "
            "\"travel_dates\": \"...\", \"travelers\": N, \"budget\": N, "
            "\"activities\": [\"...\", \"...\"], \"summary\": \"one sentence\"}, "
            "\"confidence\": 0.0-to-1.0}\nRequest: "
            + json.dumps(request)
        )
        extracted = data.get("extractedData") or fallback_data
        confidence = float(data.get("confidence", 0.5))
    except Exception as exc:
        logger.warning("extract LLM failed, using fallback: %s", exc)
        extracted = fallback_data
    ready = bool(event.get("origin") and event.get("destination")
                 and event.get("travel_dates"))
    return {"statusCode": 200, "extractedData": extracted,
            "confidence": confidence, "ready_for_coordination": ready}


def _gate(weather_data: dict, flight_data: dict):
    """Deterministic booked / needs_human_review decision."""
    if (weather_data.get("statusCode") != 200
            or flight_data.get("statusCode") != 200):
        return "needs_human_review", "Upstream agent returned an error."
    if not flight_data.get("best_option"):
        return "needs_human_review", "No flight options were found."
    if weather_data.get("risk_level") == "HIGH":
        return "needs_human_review", "High weather risk."
    if not flight_data.get("within_budget"):
        return "needs_human_review", "Best option exceeds the budget."
    return "booked", "Low weather risk and a suitable flight within budget."


def analyze_and_decide(event: dict) -> dict:
    """Analyze weather + flight data, decide auto-book or human review."""
    weather_data = event.get("weather_data") or {}
    flight_data = event.get("flight_data") or {}
    decision, reason = _gate(weather_data, flight_data)

    confirmation = None
    booking_status = "pending_review"
    if decision == "booked":
        best = flight_data["best_option"]
        confirmation = book_flight(best["flight_no"],
                                   event.get("bookingID", "trip"))["confirmation"]
        booking_status = "confirmed"

    try:
        prose = _model_json(
            "A travel planner must explain a booking decision. Reply with ONLY JSON: "
            "{\"message\": \"one or two sentences for the traveller\"}.\n"
            "Decision: " + decision + ". Reason: " + reason + ".\n"
            "Weather: " + json.dumps(weather_data.get("weather_analysis")) +
            ". Flight: " + json.dumps(flight_data.get("best_option"))
        )
        message = str(prose.get("message") or reason)
    except Exception as exc:
        logger.warning("analyze_and_decide LLM failed, using code prose: %s", exc)
        message = reason

    logger.info("decision=%s reason=%s booking=%s", decision, reason, booking_status)
    return {"statusCode": 200, "decision": decision,
            "decision_reason": reason, "booking_status": booking_status,
            "booking_confirmation": confirmation, "message": message}


def finalize_booking(event: dict) -> dict:
    """Book after human approval via the Activity."""
    flight_data = event.get("flight_data") or {}
    approval = event.get("human_approval") or {}
    best = flight_data.get("best_option")
    if not best:
        return {"statusCode": 500, "booking_status": "error",
                "booking_confirmation": None,
                "message": "No flight option available to finalize."}
    confirmation = book_flight(best["flight_no"],
                               event.get("bookingID", "trip"))["confirmation"]
    try:
        prose = _model_json(
            "A human approved this booking. Reply with ONLY JSON: "
            "{\"message\": \"one sentence confirming the booking for the "
            "traveller\"}.\nHuman approval: " + json.dumps(approval) +
            ". Flight: " + json.dumps(best)
        )
        message = str(prose.get("message") or "Booking confirmed.")
    except Exception as exc:
        logger.warning("finalize_booking LLM failed: %s", exc)
        message = "Booking confirmed after human approval."

    logger.info("finalized booking %s", confirmation)
    return {"statusCode": 200, "booking_status": "confirmed",
            "booking_confirmation": confirmation, "message": message}


_ACTIONS = {"extract": extract, "analyze_and_decide": analyze_and_decide,
            "finalize_booking": finalize_booking}


def handler(event, _context):
    try:
        init_telemetry("orch-planner-agent")
        action = event.get("action")
        fn = _ACTIONS.get(action)
        if fn is None:
            logger.error("unknown action: %s", action)
            return {"statusCode": 400, "error": f"unknown action: {action}"}
        return fn(event)
    except Exception as exc:
        logger.error("orch-planner handler failed: %s", exc, exc_info=True)
        return {"statusCode": 500, "error": str(exc)}

"""Orchestration v2: the flight manager as a pure task (action=search).

Returns exactly the shape the Parallel branch's ResultSelector reads:
{statusCode, flights_found, flight_options, best_option, within_budget}.
Uses the same deterministic mock provider as agents/flight.py."""
import logging
import os
import re

from agents.flight import search_flights
from agents.telemetry import init_telemetry

logger = logging.getLogger(__name__)


def _depart_date(travel_dates) -> str:
    """Pick the outbound date from a range string like '2026-09-21 to 2026-09-24'."""
    if not travel_dates:
        return ""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(travel_dates))
    return match.group(1) if match else str(travel_dates)


def _score(flight: dict, preference: str) -> int:
    score = 0
    pref = (preference or "").lower()
    if flight.get("direct") and "direct" in pref:
        score += 2
    return score


def search(event: dict) -> dict:
    origin = event.get("origin") or "unknown"
    destination = event.get("destination") or "unknown"
    depart = _depart_date(event.get("travel_dates"))
    preference = event.get("airline_preference") or ""
    budget = event.get("budget")

    options = search_flights(origin, destination, depart)
    if not options:
        return {"statusCode": 200, "flights_found": 0, "flight_options": [],
                "best_option": None, "within_budget": False}

    scored = sorted(options, key=lambda f: (-_score(f, preference), f["price_gbp"]))
    best = scored[0]
    within = (budget is None) or (best["price_gbp"] <= int(budget))

    logger.info("flight search %s->%s: %d options, best=%s within_budget=%s",
                origin, destination, len(options), best.get("flight_no"), within)
    return {"statusCode": 200, "flights_found": len(options),
            "flight_options": options, "best_option": best, "within_budget": within}


def handler(event, _context):
    try:
        init_telemetry("orch-flight-agent")
        if event.get("action") != "search":
            return {"statusCode": 400, "error": f"unknown action: {event.get('action')}"}
        return search(event)
    except Exception as exc:
        logger.error("orch-flight handler failed: %s", exc, exc_info=True)
        return {"statusCode": 500, "error": str(exc)}

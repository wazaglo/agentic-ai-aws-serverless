# `src/agents/`: shared agent brains

The reusable agent logic called by **both** modules. Each file wraps one
Strands `Agent` (Amazon Bedrock Nova Lite) behind a plain Python function.
No handler logic. NOevent knowledge, the `choreography/` and `orch/`
packages own coordination.

| File | Role | Used by |
|---|---|---|
| `planner.py` | `plan_trip(request) -> dict` — free-text travel request → structured itinerary JSON | choreography PlannerAgent |
| `weather.py` | `check_weather(itinerary) -> dict` — Open-Meteo forecast + deterministic `PROCEED`/`RECONSIDER` advisory; also exposes the `get_forecast` tool used by Module 2 | both modules |
| `flight.py` | `search_flights` / `book_flight` tools (deterministic mock provider) and `book_trip_flight` agent flow | both modules |
| `telemetry.py` | `init_telemetry(name)` — one-time Strands OpenTelemetry setup; console exporter by default, OTLP if `OTEL_EXPORTER_OTLP_ENDPOINT` is set | every agent |

Design notes:

- **Deterministic mock flight provider.** Prices, flight numbers and
  confirmation codes are derived from `sha256(origin|destination|date)` - 
  the demo never books real seats, never calls a paid API, and is reproducible.
  Swap the two `@tool` functions for a GDS/partner API and nothing else changes.
- **Deterministic weather gate.** `worst_precip < RAIN_THRESHOLD` (default 60%,
  env-configurable) decides the advisory; the LLM only writes the summary.
- **Module-level agent caching.** `_get_agent()` keeps the Strands agent warm
  across Lambda warm invocations.
- Agents raise on invalid input; the caller's handler decides what to return.

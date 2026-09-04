# `src/orch/` — Module 2: state-machine workers

Three Lambda handlers invoked by the Step Functions state machine
`travel-booking-orchestration`. Each is a **pure task**: Step Functions sends
an action + payload, the handler returns the exact JSON shape the ASL's
`ResultSelector` expects. No event bus, no hidden calls — the ASL owns order,
parallelism, branching, retries and the human-in-the-loop wait.

| File | Lambda | Action(s) | Returns |
|---|---|---|---|
| `planner.py` | `orch-planner-agent` | `extract`, `analyze_and_decide`, `finalize_booking` | `{statusCode, decision, booking_confirmation, message, ...}` |
| `weather.py` | `orch-weather-agent` | `analyze` | `{statusCode, weather_analysis, risk_level, conditions, recommendation}` |
| `flight.py` | `orch-flight-manager-agent` | `search` | `{statusCode, flights_found, flight_options, best_option, within_budget}` |

The one planner, three roles:

1. **`extract`** — normalise the booking request (LLM, falls back to code on failure).
2. **`analyze_and_decide`** — `_gate()` (pure Python) decides `booked` vs
   `needs_human_review`: upstream errors, no flights, `HIGH` weather risk or
   over-budget all go to the human; low risk + in budget auto-books the mock flight.
3. **`finalize_booking`** — runs only after the human approves via the
   `human-review` Activity; mints the confirmation read by
   `BookingSuccessAfterReview`.

This package is our addition to the original workshop (which only shipped a
sequential variant). The deterministic gate is deliberate: a `Choice` state
must branch on something auditable — the LLM only writes the traveller-facing
prose and its output is always validated (`_model_json`) with a code fallback.

Every handler returns `{statusCode: 500, error}` on unexpected failure rather
than crashing, so the state machine always reaches a terminal state
(`HandleError`).

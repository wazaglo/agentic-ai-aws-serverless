# `src/choreography/`: Module 1: event-driven agents

Four Lambda handlers that coordinate purely through **domain events** on the
custom EventBridge bus `travel-agents-bus`. Nobody calls anybody: each handler
reacts to one `detail-type` and announces the next one.

```
TripRequested ─▶ planner_handler  ─▶ emits ItineraryPlanned
ItineraryPlanned ─▶ weather_handler ─▶ emits WeatherChecked
WeatherChecked  ─▶ flight_handler  ─▶ emits FlightBooked | TripAbandoned
FlightBooked / TripAbandoned ─▶ collector_handler (terminal, logs outcome)
```

| File | Reacts to | Emits |
|---|---|---|
| `planner_handler.py` | `TripRequested` (source `travel.demo`) | `ItineraryPlanned` |
| `weather_handler.py` | `ItineraryPlanned` | `WeatherChecked` |
| `flight_handler.py` | `WeatherChecked` | `FlightBooked` or `TripAbandoned` |
| `collector_handler.py` | both terminal events | - (logs the outcome) |
| `events.py` | helper: `emit(detail_type, detail)` - the **only** way these agents talk | |

Gotchas baked into the design:

- **Two event sources.** The external trigger uses `travel.demo`; agents emit
  `travel.agents`. The four rules in the CFN template match these exactly - 
  mixing them up silently breaks the chain.
- The branch (book vs. abandon) is hidden inside `flight_handler.py`. That is
  the point of choreography: order and branching are *emergent*, not declared.
  The same flow as a readable state machine is Module 2 (`../orch/`).
- Handlers return `{"ok": True/False, ...}`; failures are logged with
  stack traces and the invocation lands in the SQS dead-letter queue.

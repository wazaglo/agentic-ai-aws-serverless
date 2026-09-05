# `docs/`: documentation assets

| Path | Description |
|---|---|
| `operations.md` | Monitoring, cost breakdown, security notes, troubleshooting, workshop deltas |
| `images/` | Self-contained architecture SVGs (official AWS icons inlined) |
| `screenshots/` | Authenticated AWS console captures proving the stack is deployed and a booking ran end-to-end |

## `images/`

| File | Description |
|---|---|
| `architecture-choreography.svg` | Module 1 diagram: EventBridge chain Planner → Weather → Flight → Collector, the rain-risk branch, Bedrock calls, CloudWatch + DLQ |
| `architecture-orchestration.svg` | Module 2 diagram: state machine flow with the Parallel fan-out, budget gate, HITL activity loop and all terminal states |

The SVGs are **self-contained** (official AWS architecture icons are inlined
as base64), so they render on GitHub and offline without external requests.
Icons: `icons/` contains the original AWS Architecture Icons (48 px SVG,
from the official [AWS Architecture Icons set](https://aws.amazon.com/architecture/icons/),
free for use per AWS Content License).

## Rendering to PNG

```bash
rsvg-convert -w 1080 docs/images/architecture-orchestration.svg > /tmp/orch.png
# or
python3 -c "import cairosvg; cairosvg.svg2png(url='docs/images/architecture-orchestration.svg', write_to='/tmp/orch.png', output_width=1080)"
```

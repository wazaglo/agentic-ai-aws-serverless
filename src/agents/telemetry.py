"""One place to switch tracing on for every agent.

Strands emits OpenTelemetry spans natively: agent reasoning, each tool
call, model latency and token counts. By default we use the console
exporter, which lands structured spans in CloudWatch Logs. Set
OTEL_EXPORTER_OTLP_ENDPOINT (for example via the ADOT Lambda layer or
the CloudWatch OTLP endpoint) to export real traces instead.
X-Ray tracing on the Lambda functions and the state machine is enabled
separately in the SAM templates, so the two views complement each other.
"""
import os

_configured = False


def init_telemetry(service_name: str) -> None:
    global _configured
    if _configured:
        return
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    try:
        from strands.telemetry import StrandsTelemetry

        telemetry = StrandsTelemetry()
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            telemetry.setup_otlp_exporter()
        else:
            telemetry.setup_console_exporter()
        _configured = True
    except Exception as exc:  # never let tracing break the agent
        print(f"telemetry disabled: {exc}")

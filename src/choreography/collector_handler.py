"""Terminal listener. Logs the final outcome so a demo has somewhere to
look. In a real system this would notify the traveller or update a UI."""
import json
import logging

logger = logging.getLogger(__name__)


def handler(event, _context):
    outcome = event["detail-type"]
    detail = event.get("detail", {})
    logger.info("=== TRIP %s ===\n%s", outcome, json.dumps(detail, indent=2, default=str))
    return {"ok": True}

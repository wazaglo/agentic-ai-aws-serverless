"""Terminal listener. Logs the final outcome so a demo has somewhere to
look. In a real system this would notify the traveller or update a UI."""
import json


def handler(event, _context):
    outcome = event["detail-type"]
    print(f"=== TRIP {outcome} ===")
    print(json.dumps(event["detail"], indent=2, default=str))
    return {"ok": True}

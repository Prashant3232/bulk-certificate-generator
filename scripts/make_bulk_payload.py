"""Create a large request body to try bulk generation:

    python scripts/make_bulk_payload.py 500 > samples/bulk_500.json
    curl -X POST localhost:8000/api/v1/jobs -H 'Content-Type: application/json' -d @samples/bulk_500.json
"""
import json
import sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
payload = {
    "event_name": "Bulk Demo Workshop",
    "issuer": "Acme Academy",
    "recipients": [{"name": f"Participant {i}", "email": f"participant{i}@example.com"} for i in range(1, n + 1)],
}
print(json.dumps(payload))

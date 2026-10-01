"""Print SSE event names from the venue stream for a few seconds: python eval/sse_probe.py [API_URL] [seconds]"""
import sys
import time

import httpx

API = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 12
end = time.time() + SECONDS
counts: dict[str, int] = {}
with httpx.stream("GET", f"{API}/api/venues/riverside_hall/stream", timeout=SECONDS + 5) as r:
    for line in r.iter_lines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
            counts[name] = counts.get(name, 0) + 1
            print(f"{time.strftime('%H:%M:%S')} {name}", flush=True)
        if time.time() > end:
            break
print("counts:", counts)

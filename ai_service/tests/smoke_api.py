"""Smoke test for the RUNNING AI service (real Groq + real Earth Engine).

1. Start the server:  uvicorn ai_service.app.api.main:app --port 8000
2. In another terminal, from the project root:  python ai_service/tests/smoke_api.py
"""

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
AOI = json.loads(Path("data/aoi/cairo_box.geojson").read_text())
client = httpx.Client(base_url=BASE, timeout=180)   # /approve can take a minute
failures = 0


def check(name: str, ok: bool, detail="") -> None:
    global failures
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if not ok else ""))
    if not ok:
        failures += 1


def post(path: str, body: dict | None = None, tries: int = 2) -> httpx.Response:
    """POST, trying once more if the LLM provider timed out (502)."""
    for _ in range(tries):
        r = client.post(path, json=body)
        if r.status_code != 502:
            return r
        time.sleep(3)
    return r


# ---- 1. service is up, and only the 3 endpoints exist ----
r = client.get("/health")
check("GET /health -> 200 ok", r.status_code == 200 and r.json() == {"status": "ok"}, r.text)
paths = set(client.get("/openapi.json").json()["paths"])
check("exactly 3 endpoints", paths == {"/health", "/plans", "/plans/{plan_id}/approve"}, sorted(paths))

# ---- 2. bad input gets clear errors (no Groq or Earth Engine needed) ----
r = post("/plans", {"message": "NDVI last month"})
check("first message without aoi -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "NDVI last month", "aoi": {}})
check("broken aoi -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "add water too", "session_id": "s_fake"})
check("unknown session_id -> 404", r.status_code == 404, r.text)
r = post("/plans/plan_fake/approve")
check("unknown plan_id -> 404", r.status_code == 404, r.text)

# ---- 3. chat: first plan, then a follow-up that uses memory ----
r = post("/plans", {"message": "show me vegetation last month", "aoi": AOI})
first = r.json()
check("first message -> plan", r.status_code == 200 and first.get("type") == "plan", r.text)
if first.get("type") != "plan":
    sys.exit("Cannot continue without a first plan.")
check("plan is NDVI only", first["plan"]["indices"] == ["NDVI"], first["plan"])

r = post("/plans", {"message": "add water too", "session_id": first["session_id"]})
second = r.json()
check("follow-up -> plan", r.status_code == 200 and second.get("type") == "plan", r.text)
if second.get("type") != "plan":
    sys.exit("Cannot continue without a second plan.")
plan = second["plan"]
check("follow-up -> NDVI + NDWI", set(plan["indices"]) == {"NDVI", "NDWI"}, plan["indices"])
check("follow-up keeps the dates",
      (plan["start_date"], plan["end_date"]) == (first["plan"]["start_date"], first["plan"]["end_date"]),
      plan)
check("same session_id", second["session_id"] == first["session_id"])
check("new plan_id", second["plan_id"] != first["plan_id"])

# ---- 4. approve: real computation for both indices ----
start = time.time()
r = post(f"/plans/{second['plan_id']}/approve")
approved = r.json()
print(f"      (approve took {time.time() - start:.0f} s)")
check("approve -> 200 Feature", r.status_code == 200 and approved.get("type") == "Feature", r.text[:300])
results = approved.get("properties", {}).get("results", {})
check("results for NDVI and NDWI", set(results) == {"NDVI", "NDWI"}, list(results))
for index, res in results.items():
    stats = res.get("compute_statistics", {})
    mean, valid = stats.get("mean"), stats.get("valid_pixel_pct", -1)
    check(f"{index}: mean between -1 and 1", mean is not None and -1 <= mean <= 1, stats)
    check(f"{index}: valid_pixel_pct between 0 and 100", 0 <= valid <= 100, valid)
    check(f"{index}: map tile_url present", "{z}" in res.get("create_map_layer", {}).get("tile_url", ""))

start = time.time()
r = post(f"/plans/{second['plan_id']}/approve")
elapsed = time.time() - start
check("approve twice -> same answer, instantly", r.json() == approved and elapsed < 3, f"{elapsed:.1f} s")

# ---- 5. unsupported request -> question, not a plan ----
r = post("/plans", {"message": "what about land surface temperature?", "aoi": AOI})
q = r.json()
check("unsupported request -> question without plan_id",
      r.status_code == 200 and q.get("type") == "question" and "plan_id" not in q, r.text)

print("\nALL PASSED" if failures == 0 else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
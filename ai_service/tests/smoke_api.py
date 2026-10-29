"""Smoke test for the RUNNING AI service (real Groq + real Earth Engine).

1. Start the server:  uvicorn ai_service.app.api.main:app --port 8000
2. In another terminal, from the project root:  python ai_service/tests/smoke_api.py
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("API_BASE", "http://localhost:8000")
AOI = json.loads(Path("data/aoi/cairo_box.geojson").read_text())
DATES = {"start_date": "2026-09-01", "end_date": "2026-09-30"}
client = httpx.Client(base_url=BASE, timeout=180)
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


# ---- 1. service is up, and only the 4 endpoints exist ----
r = client.get("/health")
check("GET /health -> 200 ok", r.status_code == 200 and r.json() == {"status": "ok"}, r.text)
paths = set(client.get("/openapi.json").json()["paths"])
check("exactly 6 endpoints",
      paths == {"/health", "/plans", "/plans/{plan_id}/approve", "/plans/{plan_id}/result",
                "/plans/{plan_id}/explanation", "/plans/{plan_id}/download/{index}"},
      sorted(paths))

# ---- 2. bad input gets clear errors (no Groq or Earth Engine needed) ----
r = post("/plans", {"message": "show me vegetation", **DATES})
check("first message without aoi -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "show me vegetation", "aoi": AOI})
check("first message without dates -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "show me vegetation", "aoi": {}, **DATES})
check("broken aoi -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "show me vegetation", "aoi": AOI,
                    "start_date": "2026-09-30", "end_date": "2026-09-01"})
check("start after end -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "show me vegetation", "aoi": AOI,
                    "start_date": "2026-09-01", "end_date": "2099-01-01"})
check("future end_date -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "show me vegetation", "aoi": AOI, **DATES, "image_date": "2026-10-19"})
check("range and exact day together -> 400", r.status_code == 400, r.text)
r = post("/plans", {"message": "add water too", "session_id": "s_fake"})
check("unknown session_id -> 404", r.status_code == 404, r.text)
r = post("/plans/plan_fake/approve")
check("unknown plan_id -> 404", r.status_code == 404, r.text)

# ---- 3. chat: first plan uses the engineer's dates, follow-up uses memory ----
r = post("/plans", {"message": "show me vegetation", "aoi": AOI, **DATES})
first = r.json()
check("first message -> plan", r.status_code == 200 and first.get("type") == "plan", r.text)
if first.get("type") != "plan":
    sys.exit("Cannot continue without a first plan.")
check("plan is NDVI only", first["plan"]["indices"] == ["NDVI"], first["plan"])
check("plan uses exactly the engineer's dates",
      (first["plan"]["start_date"], first["plan"]["end_date"], first["plan"]["image_date"])
      == (DATES["start_date"], DATES["end_date"], None), first["plan"])

r = post("/plans", {"message": "add water too", "session_id": first["session_id"]})
second = r.json()
check("follow-up -> plan", r.status_code == 200 and second.get("type") == "plan", r.text)
if second.get("type") != "plan":
    sys.exit("Cannot continue without a second plan.")
plan = second["plan"]
check("follow-up -> NDVI + NDWI", set(plan["indices"]) == {"NDVI", "NDWI"}, plan["indices"])
check("follow-up keeps the dates",
      (plan["start_date"], plan["end_date"]) == (DATES["start_date"], DATES["end_date"]), plan)
check("same session_id", second["session_id"] == first["session_id"])
check("new plan_id", second["plan_id"] != first["plan_id"])

# ---- 4a. approve (async): 202 now, then poll GET /result ----
plan_id = second["plan_id"]
r = client.get(f"/plans/{plan_id}/result")
check("result before approve -> 409", r.status_code == 409, r.text)
r = client.get("/plans/plan_fake/result")
check("result of unknown plan -> 404", r.status_code == 404, r.text)

start = time.time()
r = client.post(f"/plans/{plan_id}/approve")
check("approve -> 202 running, immediately",
      r.status_code == 202 and r.json().get("status") == "running" and time.time() - start < 3, r.text)

seen_progress = False
while True:
    body = client.get(f"/plans/{plan_id}/result").json()
    if body.get("status") != "running" or time.time() - start > 300:
        break
    seen_progress = seen_progress or "progress" in body
    time.sleep(2)
print(f"      (analysis took {time.time() - start:.0f} s)")
check("progress reported while running", seen_progress)
check("status ends as done", body.get("status") == "done", str(body)[:300])

approved = body.get("result", {})
check("result is a Feature", approved.get("type") == "Feature", str(approved)[:300])
results = approved.get("properties", {}).get("results", {})
check("results for NDVI and NDWI", set(results) == {"NDVI", "NDWI"}, list(results))
for index, res in results.items():
    stats = res.get("compute_statistics", {})
    mean, valid = stats.get("mean"), stats.get("valid_pixel_pct", -1)
    check(f"{index}: mean between -1 and 1", mean is not None and -1 <= mean <= 1, stats)
    check(f"{index}: valid_pixel_pct between 0 and 100", 0 <= valid <= 100, valid)
    check(f"{index}: map tile_url present", "{z}" in res.get("create_map_layer", {}).get("tile_url", ""))
    day = res.get("select_image", {}).get("date", "")
    check(f"{index}: image inside the engineer's dates",
          DATES["start_date"] <= day <= DATES["end_date"], day)

r = client.post(f"/plans/{plan_id}/approve")
check("approve again -> no restart, already done", r.json().get("status") == "done", r.text)
r = client.get(f"/plans/{plan_id}/result")
check("result again -> same answer", r.json().get("result") == approved)

# ---- 4b. explanation (separate endpoint) ----
r = client.get(f"/plans/{first['plan_id']}/explanation")
check("explanation before the analysis is done -> 409", r.status_code == 409, r.text)
r = client.get("/plans/plan_fake/explanation")
check("explanation of unknown plan -> 404", r.status_code == 404, r.text)

r = client.get(f"/plans/{plan_id}/explanation")
explained = r.json()
expl = explained.get("explanations", {})
check("explanation -> 200 for NDVI and NDWI", r.status_code == 200 and set(expl) == {"NDVI", "NDWI"},
      r.text[:300])
check("each explanation has a summary and data_quality",
      all("summary" in e and "data_quality" in e for e in expl.values()), expl)
start = time.time()
r = client.get(f"/plans/{plan_id}/explanation")
check("explanation again -> same answer, instantly",
      r.json() == explained and time.time() - start < 3, f"{time.time() - start:.1f} s")

# ---- 4c. GeoTIFF download ----
r = client.get(f"/plans/{first['plan_id']}/download/NDVI", follow_redirects=False)
check("download before the analysis is done -> 409", r.status_code == 409, r.text)
r = client.get(f"/plans/{plan_id}/download/NDBI", follow_redirects=False)
check("download of an index not in the plan -> 404", r.status_code == 404, r.text)
r = client.get(f"/plans/{plan_id}/download/NDVI", follow_redirects=False)
location = r.headers.get("location", "")
check("download -> 307 redirect to Earth Engine",
      r.status_code == 307 and "earthengine.googleapis.com" in location, r.text)
r = client.get(location) if location else r
check("the link returns a GeoTIFF file", r.status_code == 200 and len(r.content) > 1000, r.status_code)

# ---- 5. unsupported request -> question, not a plan ----
r = post("/plans", {"message": "what about land surface temperature?", "aoi": AOI, **DATES})
q = r.json()
check("unsupported request -> question without plan_id",
      r.status_code == 200 and q.get("type") == "question" and "plan_id" not in q, r.text)

# ---- 6. one exact day ----
r = post("/plans", {"message": "show me buildings", "aoi": AOI, "image_date": "2026-10-19"})
day_plan = r.json().get("plan", {})
check("exact day -> plan with that day",
      (day_plan.get("image_date"), day_plan.get("start_date"), day_plan.get("end_date"))
      == ("2026-10-19", "2026-10-19", "2026-10-19"), r.text)
check("exact day -> NDBI", day_plan.get("indices") == ["NDBI"], day_plan)

# ---- 7. a later message can change the dates in text ----
r = post("/plans", {"message": "show me vegetation", "aoi": AOI, **DATES})
chat = r.json()
r = post("/plans", {"message": "use only 26 September 2026", "session_id": chat.get("session_id")})
moved = r.json().get("plan", {})
check("dates typed in a follow-up are used",
      (moved.get("image_date"), moved.get("start_date"), moved.get("end_date"))
      == ("2026-09-26", "2026-09-26", "2026-09-26"), r.text)

print("\nALL PASSED" if failures == 0 else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)
# Satellite Indices Agent

An agent that turns engineers' plain-language requests into validated analysis plans,
and deterministic tools on Google Earth Engine that compute satellite indices
(NDVI, NDWI, NDBI) for an uploaded area.

## Team

| Member | Area | Folder |
|---|---|---|
| Mayar | Agent reasoning | `ai_service/app/agent/` |
| Shahd | Agent tools and evaluation, Earth Engine | `ai_service/app/analysis/` |
| Somaya | Indices, registry, validation | `ai_service/app/registry/` |
| Bassant | Backend API and database (Node.js) | `backend/` |
| Farah | Web app | `frontend/` |

## Folder layout

- `ai_service/`: all Python code (Earth Engine tools, agent, registry). Runs as its own service.
- `backend/`: the Node.js backend the web app talks to; it calls `ai_service`.
- `frontend/`: the web app
- `notebooks/`: experiments only
- `docs/`: architecture and decision records
- `data/`: small sample areas only (not uploaded)

## Setup (AI service)

**You need:** Python 3.12, a Google Earth Engine Cloud project (Earth Engine API enabled), and a Groq API key.

> ⚠️ The registry module (`ai_service/app/registry/`) is pending merge. Until it lands, the service can't start from a fresh clone.

**Option A: uv (recommended)**
```bash
git clone https://github.com/mayar22mostafa/satellite-indices-agent.git
cd satellite-indices-agent
uv sync
source .venv/bin/activate
```

**Option B: pip**
```bash
git clone https://github.com/mayar22mostafa/satellite-indices-agent.git
cd satellite-indices-agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Then (both options):**
```bash
cp .env.example .env                              # then fill in your values
python -c "import ee; ee.Authenticate()"          # log in to Earth Engine once
uvicorn ai_service.app.api.main:app --port 8000   # start the API
```
Open http://localhost:8000/docs to see and try the endpoints.

**Check that everything works** (server running, in a second terminal):
```bash
python ai_service/tests/smoke_api.py
```

**When you add a package:** `uv add <package>`, then regenerate the pip file so both stay in sync:
```bash
uv export --no-hashes --no-dev --no-emit-project -o requirements.txt
```

## Working rules

- Feature branches merge into `develop`; `develop` merges into `main` at the end of each sprint.
- `main` and `develop` are protected: every change goes through a pull request with one review.
- Branch names: `feat/<area>-<short-name>`, for example `feat/agent-planner`.
- Never commit secrets: keys live in `.env`, which is never uploaded.
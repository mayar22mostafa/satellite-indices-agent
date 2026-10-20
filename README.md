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

## How to run the AI service

```bash
uv sync
source .venv/bin/activate
python -c "import ee; ee.Authenticate()"
python -m ai_service.app.analysis.pipeline --aoi cairo_box --index NDVI
```

Needs a `.env` file (copy `.env.example`) with `EE_PROJECT` set, and an area file in `data/aoi/`.

## Working rules

- Feature branches merge into `develop`; `develop` merges into `main` at the end of each sprint.
- `main` and `develop` are protected: every change goes through a pull request with one review.
- Branch names: `feat/<area>-<short-name>`, for example `feat/agent-planner`.
- Never commit secrets: keys live in `.env`, which is never uploaded.
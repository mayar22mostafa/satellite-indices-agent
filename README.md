# Satellite Indices Agent

An agent that turns engineers' plain-language requests into validated analysis plans,
and deterministic tools on Google Earth Engine that compute satellite indices
(NDVI, NDWI, NDBI) for an uploaded area.

## Team

| Member | Area | Folder |
|---|---|---|
| Mayar | Agent reasoning | `backend/app/agent/` |
| Shahd | Agent tools and evaluation, Earth Engine | `backend/app/analysis/` |
| Somaya | Indices, registry, validation | `backend/app/registry/` |
| Bassant | API and database | `backend/app/api/`, `backend/app/db/` |
| Farah | Web app | `frontend/` |

## Folder layout

- `backend/app/`: all backend code (API, agent, analysis tools, registry, database)
- `frontend/`: the web app
- `notebooks/`: experiments only
- `docs/`: architecture and decision records
- `data/`: small sample areas only

## How to run

Coming soon.

## Working rules

- Feature branches merge into `develop`; `develop` merges into `main` at the end of each sprint.
- `main` and `develop` are protected: every change goes through a pull request with one review.
- Branch names: `feat/<area>-<short-name>`, for example `feat/agent-planner`.
- Never commit secrets: keys live in `.env`, which is never uploaded.
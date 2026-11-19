# Gully11

Cricket fan web app: player stats, an all-time XI builder with simulated series, and a real-time IPL-rules auction — all running off one player database and one match simulator. Full plan: [docs/PLAN.md](docs/PLAN.md).

## Layout

| Folder | What | Stack |
| --- | --- | --- |
| `pipeline/` | Cricsheet download → one-row-per-delivery Parquet → DuckDB aggregates → Postgres | Python, DuckDB, PyArrow |
| `api/` | REST + WebSocket API, simulator, auction engine | FastAPI |
| `web/` | Frontend | Next.js, TypeScript, Tailwind |
| `docs/` | Plan and design notes | |

## Getting started

Requires Docker, Node 22+, and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up -d            # Postgres 16 (+pg_trgm) and Redis

# Data pipeline
cd pipeline
uv sync
uv run gully-pipeline download --dataset ipl     # or: all
uv run gully-pipeline parse --dataset ipl
uv run pytest

# API
cd ../api
uv sync
uv run uvicorn gully_api.main:app --reload       # http://localhost:8000/api/v1/health

# Web
cd ../web
npm run dev                                      # http://localhost:3000
```

## Data credits

Match data from [Cricsheet](https://cricsheet.org/), licensed under the [Open Data Commons Attribution License](https://cricsheet.org/licensing/). Player batting/bowling styles from Wikipedia (CC BY-SA 4.0).

# Gully XI

[![CI](https://github.com/sha728/gully11/actions/workflows/ci.yml/badge.svg)](https://github.com/sha728/gully11/actions/workflows/ci.yml)

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
uv run gully-pipeline download --dataset all     # ~150 MB; or: ipl / tests / odis / t20s
uv run gully-pipeline parse --dataset all        # -> data/parquet/all (~4 min)
uv run gully-pipeline build --dataset all        # -> data/gully.duckdb player tables
uv run gully-pipeline load                       # -> Postgres (drops + reloads player tables)
uv run gully-pipeline spotcheck                  # recount 10 players from raw JSON, diff vs tables
uv run gully-pipeline legends                    # rebuild reference/legends.csv (needs WIKIMEDIA_CONTACT)
uv run gully-pipeline names                      # full names + nationality from Wikidata -> reference/ (needs WIKIMEDIA_CONTACT)
uv run gully-pipeline styles                     # batting hand + bowling style from Wikipedia -> reference/ (needs a build; rebuild after)
uv run gully-pipeline simbase                    # simulator base rates -> api/src/gully_api/sim/data/
uv run gully-pipeline auction2026                 # IPL 2026 auction + retentions from Wikipedia (needs WIKIMEDIA_CONTACT)
uv run pytest

# API
cd ../api
uv sync
uv run uvicorn gully_api.main:app --reload       # http://localhost:8000/docs
uv run pytest                                    # player tests skip if Postgres isn't loaded
uv run python scripts/validate_sim.py --fit 2024 2025 --years 2026 2026   # simulator vs real IPL

# Web
cd ../web
npm run dev                                      # http://localhost:3000: search, player, compare, venue pages
npm run preview                                  # production build + server: much faster for just using the app
```

**Nationality.** A player's country is the side they played internationals for in
Cricsheet. Where there's none (uncapped players, and Afghanistan, which Cricsheet
has no men's matches for), it falls back to, in order: hand-checked fixes in
`pipeline/reference/nationality_fixes.csv`; Wikidata's country for sport, then
citizenship, as a cricket team name (`gully-pipeline names`); and India for anyone
who has played the Syed Mushtaq Ali Trophy. About 1,900 of 10,252 players, mostly
lower-profile county and associate players, still have none.


Dev mode compiles each page on first visit and doesn't cache, so it's slow to click
around in; `npm run preview` serves pages in tens of milliseconds. The web app calls the
API at `http://127.0.0.1:8000` (override with `NEXT_PUBLIC_API_URL`): on Windows,
`localhost` tries IPv6 first and every call waits ~0.2 s before falling back to the
IPv4 address Uvicorn listens on.

## Deploying

The dev site runs on Vercel (web), Render (API) and Neon (Postgres), all on free plans: see [docs/deploy.md](docs/deploy.md).

## CI

- **CI** (`.github/workflows/ci.yml`, every PR and push to `main`): pipeline tests, API +
  simulator tests (database tests skip), web type check, lint and production build. No
  data downloads, so it stays fast.
- **Integration** (`.github/workflows/integration.yml`, weekly and on demand): runs the
  whole pipeline into a Postgres service, then the API tests with `REQUIRE_DB=1` (missing
  data fails instead of skipping) and an informational simulator check against the latest
  IPL season.
  - cricsheet.org challenges CI servers, so the workflow reads the newest `data-YYYY-MM-DD`
    [release](https://github.com/sha728/gully11/releases) of this repo: the same two
    Cricsheet files, published from a normal machine.
  - To refresh it, run `gully-pipeline download --dataset all` then `gully-pipeline snapshot`.

Work happens on feature branches merged into `main` through pull requests.

## Data credits

Match data from [Cricsheet](https://cricsheet.org/), licensed under the [Open Data Commons Attribution License](https://cricsheet.org/licensing/). Full player names from Wikidata (CC0). Pre-2001 legends' career figures and player batting/bowling styles from Wikipedia (CC BY-SA 4.0); each row of `pipeline/reference/legends.csv` links the exact article revision it was read from.

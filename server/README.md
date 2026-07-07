# LifeOS — server

Python + FastAPI + PostgreSQL. Canonical datastore and authoritative scoring
engine (spec §4.2). Phase 1 scope: **data model + scoring engine only** — no iOS,
no web, no external integrations.

## Layout

```
app/
  config.py      Settings (.env) + ScoringConfig (all TUNABLE constants, spec §7/§8)
  db.py          SQLAlchemy engine/session
  models/        ORM mirroring spec §6 (the full schema)
  scoring/       PURE, DB-free scoring engine (added in Phase 1 step 3)
  seed/          §22 seed data + runner
  api/           thin FastAPI app (health only in Phase 1)
migrations/      Alembic
tests/           scoring proofs (step 4)
sim/             day-by-day simulation harness (step 4)
```

The scoring engine (`app/scoring/`) imports nothing from the DB and runs with zero
external services, so all scoring tests and the sim harness need no Postgres.

## Local setup

```bash
# 1. Deps (uv recommended; plain pip shown for portability)
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -e ".[dev]"

# 2. Postgres (canonical store)
docker compose up -d db

# 3. Config
cp .env.example .env        # defaults already match docker-compose

# 4. Migrate + seed
alembic upgrade head
python -m app.seed.run_seed

# 5. Tests (no DB needed for scoring)
pytest
```

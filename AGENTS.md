# LifeOS — Codex Project Rules

LifeOS is a single-user, local-first "life OS": gamified habit/system tracking plus fitness, nutrition, sleep, calendar, and personal finance, with an esports-style ranking system. Solo build, ADHD-first design.

**Source of truth: `docs/SPEC.md`.** Read it before implementing. This file holds only the invariants; the spec holds the detail. If code and spec conflict, the spec wins — or ask.

## Stack & layout
- `/server` — Python + FastAPI + PostgreSQL (canonical datastore, authoritative scoring recompute, food agent, finance, web API)
- `/ios` — Swift/SwiftUI (primary client, offline-first; HealthKit / EventKit / push)
- `/web` — React PWA (desktop dashboard)
- `/docs` — SPEC.md and design notes

## Non-negotiable invariants
1. **Never hardcode identifiers that drift** — LLM model strings, the IRS Roth contribution limit, Apple entitlement names, Actual/SimpleFIN endpoints. Read from config/`.env`; look up current values, don't freeze them.
2. **Server is canonical; the phone is autonomous.** Daily logging and scoring must work fully offline; the server's post-merge recompute is authoritative on sync. Never make logging depend on connectivity.
3. **Rank rises only from doing the thing.** No mechanic (Day Mode, mulligan, reward) may turn a miss into a win — only into neutral or a reduced expectation.
4. **Scoring is deterministic** — a pure function of logs + config, so any node agrees once synced. No hidden state; make it re-computable from `day_evaluations`.
5. **Never commit secrets.** Use `.env` (+ `.env.example`). Finance/health data encrypted at rest.

## Workflow
- Build in small, reviewable diffs. Commit often. Explain the plan before large changes; ask when a decision isn't in the spec.
- **The scoring engine is test-driven:** write tests first and prove the equilibrium / decay / season math on synthetic logs before any UI exists. Tests must pass before moving on.
- Prefer editing over rewriting; keep changes scoped to the current build phase (spec §23).
- Don't invent a large subsystem to fill a gap — flag it and record the choice in `DECISIONS.md`.

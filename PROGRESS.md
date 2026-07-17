# PROGRESS.md

High-signal map of where the build is and what's next. Details live in `DECISIONS.md`
and `docs/SPEC.md` (§23 is the build sequence). This file is the orientation, not a log.

## Current state — Phase 1 food quick-log API

The base before this slice was committed core + invariant hardening at `301d761`. The
server-side food quick-log slice is implemented. Run `docker compose up -d db` then
`pytest`. Pure scoring tests need no DB; integration tests use a throwaway `lifeos_test`
DB on the `lifeos-db` container.

Current verification: **86 tests green** (58 pure + 28 integration/API); one pre-existing
Starlette/httpx deprecation warning.

- **Data model + migration** — full spec §6 schema (33 tables), Alembic (`migrations/`).
- **Seed** — §22 data (domains, Morning Routine, starter habits/phases, 7 Day Modes,
  4-day plan, finance placeholders, Season 1). Idempotent.
- **Scoring engine** (`app/scoring/`) — pure, DB-free, deterministic (§7–§9): performance
  score + grace, rolling baseline, Day Mode resolution, domain gain−decay equilibrium with
  mass normalization, LP↔tier ladder, season soft-reset, mulligan math, XP/levels/tokens.
  Runs on `config.ACTIVE_SCORING` (base 175 / decay 0.025 / mass-normalized). Sim harness
  in `sim/`.
- **Adapter** (`app/adapter/`) — deterministic day-close: replays `logs + config` and
  persists `day_evaluations` / `rank_state` / `xp_ledger` / `account_level` / `rank_peaks`
  as a recomputable cache (§20 inv. 4). Idempotent.
- **API** (`app/api/main.py`) — `GET /health`, `POST /logs`, `POST /day-close/{day}`,
  `GET /rank`, `POST|GET /day-assignments` (Day Modes), `POST /mulligans` (§8.3 spend),
  `POST /meals`, `POST|GET /meal-templates`, and template re-log with portion scaling.
- **Invariant hardening** — season resets never promote; already-scored
  days can be reclassified only through the paid/never-win mulligan path; replay respects
  target expectation windows and includes silent scheduled days.
- **Food quick-log** — manual/voice/pre-computed-photo capture persists
  meals and canonical macro logs; explicit templates round-trip; re-log scales calories
  and protein by ×0.5–×2; optional client UUID retries do not duplicate macro logs.

## Remaining build slices (ordered, per SPEC §23)

### Slice 1 — Foundation + core loop (finish)
Server core is done. Left:
- [x] **Day Modes over API** — apply/list `day_assignments`; day-close honors overrides;
      §9.1 anti-exploit (retroactive rejected without a mulligan).
- [x] **Mulligan spend API** — §8.3: `POST /mulligans` neutralizes a past day or applies a
      mode retroactively; server-side cost ladder + monthly cap; XP lifetime vs spendable;
      never a win. Unlocks the retroactive path the day-assignments endpoint gates.
- [x] **Rank invariant hardening** — reset never promotes; scored-day modes require the
      paid path; historical replay honors target expectation windows.
- [x] **Food quick-log API** — manual + one-tap template re-log with honest portion
      scaling; photo capture accepts pre-computed macros behind a Slice-3 resolver seam.
- [ ] **iOS app** — Swift/SwiftUI shell, on-device SQLite (GRDB) mirror, sync queue,
      on-device scoring at day-close. *(native; separate track)*

### Slice 2 — Gamification polish + body/fitness capture
- [ ] Tier UI, promotion/demotion moments, notifications.
- [ ] HealthKit: sleep-driven day-close, cardio, weight + 7-day EMA smoothing.
- [ ] Fast lift entry + ad-hoc logging; JSON plan import with preview/diff; e1RM trends.

### Slice 3 — Nutrition agent (for real)
- [ ] Server vision agent (Anthropic, model string from docs at build time), model tiering,
      meal memory (`meal_templates`), voice notes.

### Slice 4 — Finance
- [ ] Actual Budget + SimpleFIN pull; transaction cache; allocation waterfall; Finance rank
      (rewards staying within budgets incl. fun money); Roth-headroom (current-year IRS
      limit at build time); LLM auto-categorizer.

### Slice 5 — Calendar + report + polish
- [ ] EventKit read; LifeOS-owned calendar auto-blocking for systems; weekly girlfriend
      report; web dashboard depth; backups hardened.

## Deferred (revisit in the owning slice)
- Engine: `floating_count` scheduling, severe-Sick toggle, `expect_more` target-raising.
- Adapter: store the active `ScoringConfig`/version in DB; full timezone handling for
  timing windows (currently wall-clock of `logged_at`); `rank_peaks` for `habit` scope.
- Scoring constants are **Season-1 tunables** — recalibrate after living one reset (§25).
- Known review findings and their scheduled owning slices are recorded in `DECISIONS.md`
  under “Known findings — scheduled, not fixed in this slice.” Phase-2 iOS sync owns the
  client UUID/dedupe contract, DB uniqueness/idempotency constraints, and ingestion
  validation group.

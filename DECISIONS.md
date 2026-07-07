# DECISIONS.md

Running log of choices made where the spec left a detail open, per `CLAUDE.md` and
spec §0/§25 ("prefer a small, reversible, well-commented choice and record it here").

Format: **[date] — decision — rationale / where.**

---

## Phase 1 — Foundation (data model + scoring engine)

### Architecture & tooling

- **2026-07-07 — Scoring engine is a pure, DB-free package (`app/scoring/`).** It
  takes plain dataclasses (logs + `ScoringConfig`) and returns evaluations, importing
  nothing from SQLAlchemy/Postgres. *Why:* spec §4.1/§20 require the same deterministic
  engine to run on the phone offline; §invariant 4 requires re-computability. Consequence:
  all scoring tests + the sim harness run with zero external services. (Engine itself
  lands in Phase 1 step 3.)

- **2026-07-07 — All TUNABLE constants live in one frozen `ScoringConfig`**
  (`app/config.py`), seeded with spec defaults. *Why:* Season 1 is a calibration run
  (§25); recalibration must be swapping a config, never editing engine logic.

- **2026-07-07 — Stack: SQLAlchemy 2.0 + Alembic + Postgres 16, pip/venv.** `uv` is
  not installed on the build machine, so we used `python -m venv` + `pip install -e`;
  `pyproject.toml` is still uv-compatible. Local Postgres via `docker-compose.yml`
  (`postgres:16`); the owner had none running.

- **2026-07-07 — Full §6 schema in one initial migration** (33 tables). Fitness,
  nutrition, finance, and calendar tables exist but are **inert** in Phase 1 — only
  `exercises` / `lift_plans` / `lift_plan_entries` (seed plan) and `fin_budgets`
  (placeholders) get rows. *Why:* §6 is decision-complete; building a subset now just
  forces a re-migration later. Verified: migrate → seed → downgrade→base → upgrade→head
  all clean; seed is idempotent.

### Spec / repo notes

- **2026-07-07 — Spec path mismatch.** `CLAUDE.md` says the source of truth is
  `docs/SPEC.md`; the file is actually `docs/LifeOS-Specification.md`. Left `CLAUDE.md`
  untouched (it holds invariants — not editing without owner sign-off). **Open:** rename
  the spec to `docs/SPEC.md` or fix the pointer in `CLAUDE.md`.
- Spec has no §12 (numbering jumps §11 → §13). Cosmetic; ignored.

### Filled-in values (spec left "TUNABLE"/placeholder without a number)

- **`NEW_HABIT_BASELINE_ANCHOR = 0.0`.** §7.2 says new habits (<7 days) use "a low
  anchor so early completions are strong wins and early misses cost nothing" but gives
  no number. `0.0` makes any completion beat baseline (strong early win); the §7.2
  grace clamp `gain = max(0, gain)` independently guarantees early misses can't hurt.
- **`ladder_midpoint_lp = 1400.0`.** §7.8 compresses toward "the ladder midpoint" but
  never defines it. Iron I..Diamond IV = 7 tiers × 4 divisions × 100 LP = 2800; midpoint
  = 1400. TUNABLE; will be revisited when the LP↔tier ladder is built (step 3) and after
  the Season 1 reset is lived through.
- **Nutrition "Bulk" phase placeholders:** Protein `160 g`, Calories `2800 kcal`,
  `effective_from = 2026-07-07`. §22 explicitly says the **owner sets** these; seeded
  only so the app is usable immediately. Bulk starts "today" rather than at the season
  boundary since the summer bulk predates Season 1 (2026-08-20).

### Seed modeling choices (§22 / §9.3)

- **Day Mode prose → concrete override op/factor.** §9.3 describes effects in prose;
  seeded overrides interpret them as (owner tunes by feel):
  - *Weekday:* no overrides (full structure).
  - *Weekend:* `neutralize_timing` on Morning Routine (system) + Wake time (habit);
    nutrition untouched (stays full weight).
  - *Travel:* `pause` Fitness domain; `scale_target ×0.6` Protein; `neutralize_timing`
    Sleep domain.
  - *Vacation:* `scale_target ×0.7` Nutrition domain (relaxed); `neutralize_timing`
    Sleep. Nothing paused. ("Over-target not penalized" is `COMPLETION_CAP` engine
    behavior, not a seed override.)
  - *Competition:* `pause` Fitness + `pause` Nutrition (neutralized); `scale_importance
    ×1.5` Wake time; reminder "Eat before you compete."
  - *Sick:* seeded as **mild** — `scale_target ×0.5` on Fitness + Nutrition, `params
    {severity: mild}`. **Severe → pause is a runtime toggle**, not a separate seed mode
    (open: decide whether severe is a second mode or a per-assignment param).
  - *Going Out:* `neutralize_timing` Sleep; `scale_importance ×0.6` Nutrition with a
    params note ("drink calories logged but not penalized").
- **Morning Routine steps are inline labels** (`system_steps.inline_label`), not linked
  habits — they aren't independently scored habits. The separate "Brush teeth (PM)"
  starter habit is distinct from the routine's morning "Brush teeth" step.
- **Morning Routine:** importance 3, `expected_duration_min = 30`, timing 06:00–10:00
  (§22 gave the window, not importance/duration).
- **Workout habit** modeled as `binary`, `specific_days` = MO/TU/TH/FR to match the seed
  plan; the plan drives *what* to lift, the habit drives *scored completion*.
- **`fin_budgets` given a surrogate UUID PK** (spec §6.10 implied `category` as key);
  uniform with every other table's UUID PK + soft-delete columns.
- **Finance budget amounts seeded at 0.0** (Essentials / Fun Money / Savings-Investing)
  — placeholders; owner sets amounts (§17).

### Deferred to a later step/phase (safe per §25)

- **`floating_count` schedule** ("3×/week any day", §11): schema supports it
  (`schedule_type` + `schedule_config`), but eligibility + weekly-shortfall scoring is a
  step-3 engine decision, not yet implemented. No seed habit uses it.
- Severe-Sick representation (see above).
- LP↔tier/division ladder constants beyond `ladder_midpoint_lp` (step 3).

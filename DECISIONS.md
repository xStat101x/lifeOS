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

- **2026-07-07 — Spec path mismatch → RESOLVED.** `CLAUDE.md` points to `docs/SPEC.md`;
  the file had been `docs/LifeOS-Specification.md`. Renamed to `docs/SPEC.md` (owner
  approved), so the pointer now resolves. `PHASE-1-KICKOFF.md` also moved to repo root.
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
  (`schedule_type` + `schedule_config`), but eligibility + weekly-shortfall scoring is
  not yet implemented in the engine. No seed habit uses it. Still deferred.
- Severe-Sick representation (see above).

---

## Phase 1 — Scoring engine (step 3)

### Architecture

- **2026-07-07 — Pure engine realized in `app/scoring/`** — no DB/ORM imports; operates
  on dataclasses (`types.py`) + `ScoringConfig`. 10 modules: performance (§7.2), baseline
  (§7.2), day_modes (§9), equilibrium (§7.3), ladder (§7.7), seasons (§7.8), forgiveness
  (§8.3), xp (§8), engine (orchestration/replay). 53 unit + behavioral tests, all green,
  zero external services. Sim harness in `sim/` (`python -m sim.harness`).
- **Systems score as quantitative habits** (§7.4): passed to the engine as
  `HabitSpec(is_system=True, kind='quantitative')` with value=steps_done, target=steps_total.
  No separate code path.
- **Decay suspended whenever a domain has 0 active expectations that day** — i.e. all
  scheduled targets paused *or nothing scheduled* (§7.3, §7.5). So a domain only decays on
  days it actually expected something; planned rest days never bleed LP.
- **Timing weights are NOT renormalized** when timing is absent/neutralized — the timing
  term simply drops to 0 (spec §7.2 is explicit: `W_TIMING_eff = 0`).
- **Grace window** (`age < NEW_HABIT_GRACE_DAYS`) drives BOTH the low-anchor baseline and
  the `gain = max(0, gain)` clamp, so early days can only help.
- **Mulligan modeled at domain-day granularity** (§8.3): `neutralize_domain_day` erases a
  losing day to 0; `clamp_never_win` caps a retroactively re-scored day at ≤0. Cost ladder
  (200/400/800) + monthly cap enforced by `mulligan_cost`. Never yields a win.
- **XP level curve:** advancing L→L+1 costs `xp_level_base * L` (=100·L; increasing per
  §8.2). Reward token every 10 levels. TUNABLE.
- **Apex thresholds** Master 2800 / GM 3200 / Challenger 3600 (`ScoringConfig`, TUNABLE).
- **`expect_more` currently only flags bonus-eligibility** (ModeEffect.expect_more); it
  does not yet auto-raise the target. Raising the bar needs a factor/params convention —
  **deferred** (no seed mode uses expect_more).

### ⚠ Calibration finding — spec-default constants are internally inconsistent

- **2026-07-07 — The spec's default scoring constants cannot meet the spec's own
  season-reclaim target, and invert the reset.** With `BASE_LP_SWING=15`,
  `DECAY_RATE=0.02`, `LP_PER_DIVISION=100`, `midpoint=1400`: a disciplined 2-habit domain
  (protein imp5 + calories imp4, sustained perfect) equilibrates at only **~562 LP
  (Bronze III)** — *far below* the 1400 ladder midpoint. Consequences:
  1. The season soft-reset "compress toward midpoint" (§7.8) *raises* sub-midpoint LP
     (562 → 1107), i.e. it **promotes** on reset instead of demoting — the opposite of
     the "Diamond drops to Gold" intent.
  2. Reclaim is meaningless, and with the slow decay (time-constant 50 days) any real
     re-climb would take ~150 days, not ~30.
- **This is exactly the Season-1 calibration the spec flags (§7.8, §25)** — surfaced to
  the owner, not silently patched.
- **Two levers (owner's call in Season 1):**
  - **(A) Inflate the LP economy:** raise `BASE_LP_SWING` ~10–13× and `DECAY_RATE`→~0.075
    so disciplined equilibria reach Plat/Emerald and reclaim ~30 days.
  - **(B) Shrink the ladder scale:** cut `LP_PER_DIVISION` (and midpoint/apex) ~10× and
    keep `BASE_LP_SWING` modest — same shape, smaller numbers.
- **2026-07-08 — RESOLVED: adopted lever A** (owner decision), later augmented with mass
  normalization (next entry). The engine runs on `config.ACTIVE_SCORING`
  = `replace(DEFAULT_SCORING, base_lp_swing=175.0, decay_rate=0.025, normalize_domain_mass=True)`.
  `DEFAULT_SCORING` is kept unchanged as the literal-spec reference. `Engine`, the sim
  harness, and `sim.calibration.CALIBRATION_SCORING` all point at `ACTIVE_SCORING`. The
  season-reclaim behavioral test runs on `ACTIVE_SCORING`; the other five behaviors are
  asserted on `DEFAULT_SCORING` (they're config-independent).
- **These remain Season-1 tunables, not final** (§25) — recalibrate after living through
  one reset. Lever B (shrink the ladder scale ~10× instead of inflating the swing) stays
  on the table. Run `python -m sim.calibration` to compare DEFAULT vs ACTIVE.

### Per-domain mass normalization (`normalize_domain_mass`)

- **2026-07-08 — Problem:** a domain's equilibrium LP scaled with its total habit-mass
  (Σ importance/divisor), because `gain_total` grows with the number/importance of habits
  while decay did not. So single-habit domains settled far lower and dragged the overall
  average down — full compliance everywhere still read **Silver II** (nutrition Emerald IV
  vs routines Bronze IV).
- **Fix:** scale each domain's decay by its active habit-mass
  (`decay = decay_rate · mass · (lp − floor)`), behind `ScoringConfig.normalize_domain_mass`
  (default **False** = literal-spec; **True** in `ACTIVE_SCORING`). At full compliance
  `gain_total ≈ base·perf·mass` and decay ∝ mass, so mass cancels and the equilibrium is
  **`base·perf/decay_rate`, mass-independent**. Every fully-complied domain now converges
  to the same target. `base_lp_swing` was nudged 200 → **175** so that target is
  `175·0.25/0.025` = **1750 LP (Platinum III)** — solidly mid-Platinum, clear of the
  Emerald boundary (2000) and both division edges (1700/1799), avoiding rank flicker.
  Overall full-compliance now reads Platinum III instead of Silver II.
- **Importance still governs within-domain weighting and miss severity** — per-habit
  `gain` is unchanged (`base · importance/divisor · perf`); normalization only rescales
  the domain-level decay constant.
- **Consequence (accepted):** the *effective reclaim rate* is now `decay_rate · mass`, so
  higher-mass domains reclaim faster. To keep the spec's ~30-day reclaim on a
  nutrition-scale domain (mass≈3), `decay_rate` was retuned 0.075 → **0.025** (0.025·3 =
  0.075, the prior reclaim rate). Single-habit domains reclaim proportionally slower;
  acceptable and documented. TUNABLE.
- **Before/after (from `python -m sim.calibration`):**

  | domain | before LP (rank) | after LP (rank) |
  |---|---|---|
  | nutrition | 2000 (Emerald IV) | 1750 (Platinum III) |
  | fitness | 1111 (Silver I) | 1750 (Platinum III) |
  | sleep | 667 (Bronze II) | 1750 (Platinum III) |
  | routines | 444 (Bronze IV) | 1750 (Platinum III) |
  | **overall** | **1056 (Silver II)** | **1750 (Platinum III)** |

  (Before = pre-normalization ACTIVE, base 200 / decay 0.075. After = current ACTIVE.)

### Still deferred (step 3 scope boundary)

- `floating_count` scheduling (above), severe-Sick, `expect_more` target-raising.

---

## Phase 1 — Postgres↔engine adapter

- **2026-07-08 — Adapter wraps the pure engine unchanged** (`app/adapter/`). The engine
  in `app/scoring/` was not modified. `config_loader.World` loads config + logs;
  `day_close.close_day` replays + persists; `queries.current_rank` reads back. Per-day
  phase targets (§11) are supplied by reassigning the engine's public `habits` dict before
  each `process_day` — no engine change needed.
- **Day-close = full deterministic replay** from `history_start` (earliest log ≤ target
  day) through the target day, reconstructing baselines/LP/XP purely from `logs + config`.
  The persisted rows are therefore a **recomputable cache** (§20 invariant 4): wiping
  `day_evaluations`/`rank_state`/`xp_ledger` and re-closing reproduces identical values
  (proven by `test_recomputable_from_logs_only`).
- **Idempotency:** `day_evaluations` for the day are hard-deleted then re-inserted (a pure
  cache); `xp_ledger` keeps **one row per (day, 'day_close')**, upserted; `rank_state`
  upserts per (scope, scope_id, season); `account_level` upserts. Re-running a close is a
  no-op on state (`test_day_close_is_idempotent`).
- **Config source is `ACTIVE_SCORING`** (not yet stored in the DB). Persisting the active
  config/version is a later concern; noted so scoring stays reproducible.
- **Domains with no scored targets are omitted** from ranking (Finance in Phase 1 has no
  habits/systems) — they'd otherwise sit at 0 LP and drag `overall`. They appear once they
  own a habit/system. `overall` = weighted avg over scored domains using `domains.weight`.
- **Scheduling in the loader** (§11): `daily` / `weekdays` / `specific_days`. A
  **scheduled-but-unlogged** target is scored as a **miss** (completion 0), not skipped
  (`test_scheduled_but_unlogged_is_a_miss_not_absent`). `floating_count` is treated as
  unscheduled (deferred).
- **Systems** are scheduled daily while active and scored as a quantitative target
  (`steps_done/steps_total`); `steps_done` = count of distinct `system_step` logs that day
  (or a direct `system` log's `value`).
- **Observations from logs:** quantitative habit value = **sum** of that day's logs for it;
  binary = any log ⇒ done. **Timing** uses `log.meta['timing_in_window']` if present, else
  the log's wall-clock `logged_at` vs the window (a full timezone pass is deferred, §10).
- **Season soft-reset is applied during replay** at a season boundary, and **`rank_peaks`
  is banked as the replay crosses days** (§7.8). Peaks are tracked per (season, scope) as a
  running high-water LP during the replay — not re-derived on the fly — so an ending
  season's pre-reset peak is captured exactly and stays correct even if the replay is later
  optimized. `_upsert_peak` is monotonic (never lowers a banked peak), so out-of-order
  closes can't erase one; a full recompute from wiped logs reproduces the true max
  (`test_season_reset_banks_peak_and_survives_recompute`). Both `domain` and `overall`
  scopes are banked.
- **`day_evaluations.decay`/`lp_change` are domain-level values replicated** onto each of
  that domain's target rows (the table is per-target; decay is per-domain, §7.3).
- **Endpoints** (`app/api/main.py`, `uvicorn app.api.main:app`):
  `GET /health`, `POST /logs`, `POST /day-close/{day}`, `GET /rank`.
- **Tests:** 7 integration tests run against a throwaway `lifeos_test` DB on the lifeos-db
  container (conftest provisions/seeds/drops it; pure scoring tests stay DB-free). Covers
  log→close→read round-trip, idempotent re-close, recompute-from-logs, multi-day
  accumulation, and season-reset peak-banking + recompute. `httpx` added to dev deps for
  FastAPI's `TestClient`. 64 tests total green.
- **Untouched (still deferred):** `floating_count`, severe-Sick, `expect_more`.

---

## Phase 1 — Day Modes over the API (§9)

- **2026-07-17 — `POST` / `GET /day-assignments`.** Apply a Day Mode to a day and list
  assignments. Day-close already honored assignments (the loader builds the pure `DayMode`
  from `day_assignments` + overrides and the engine resolves the `ModeEffect`), so this
  slice is the API + persistence around it — the engine and adapter were not changed.
- **One active mode per day:** applying a mode **soft-deletes** any existing assignment for
  that day, then inserts (a day resolves to a single mode). `GET` filters `deleted_at`.
- **§9.1 anti-exploit — retroactive rejected (409).** Applying a mode to **today or a
  future day is free**; applying to a **past day** (`effective_day < today`) is the mulligan
  path, which isn't wired yet, so it's rejected with a clear error naming the mulligan
  requirement. Actual mulligan-spend + the retroactive-apply path is its own later slice.
- **"Today" is a `get_today` FastAPI dependency** (returns `date.today()`), overridable in
  tests so the retroactive rule is deterministic regardless of wall clock (pinned to
  2026-08-20 = Season 1 start in the test client).
- **Verified overrides change scoring** (integration, against the container): *Travel*
  pauses Fitness (workout eval `was_paused`, domain LP unchanged) and scales Protein ×0.6
  (96 g → completion 1.0 instead of 0.6); *Weekend* neutralizes Wake-time timing (eval
  `timing` becomes `None` instead of 0.0); *Sick* scales targets ×0.5 (80 g → completion
  1.0). Each asserts the before (no mode) vs after (mode applied + re-close). The eval also
  records `applied_mode_id`.
- **Tests:** 6 new (`test_daymode_api.py`) — apply/list/replace, retroactive 409, unknown
  mode 404, and the three override behaviors. **70 tests total green.**
- **`PROGRESS.md` added** at repo root: current state + ordered remaining slices per §23.

---

## Phase 1 — Mulligan-spend over the API (§8.3, invariant 3)

- **2026-07-17 — A mulligan is recomputable source data.** `POST /mulligans` records a
  `Mulligan` row (and, for the mode path, a retroactive `day_assignment`); the *forgiveness
  itself* is applied in the **replay** (`day_close`), which reads mulligans just like logs.
  So the ladder stays re-computable from `logs + config + mulligans` (§20 inv. 4) — proven
  by `test_mulligan_survives_cache_wipe_recompute` (wipe the cache, re-close, forgiveness
  reappears).
- **Two forgiveness paths, both incapable of a win** (reuse the engine's helpers):
  - **Neutralize** (`mode_id` omitted) → `neutralize_domain_day` = `max(0, day_change)`
    per domain: the day's *losses* are erased to 0, real gains kept. Never manufactures LP.
  - **Retroactive mode** (`mode_id` set) → the day is re-scored under the mode, then
    `clamp_never_win` = `min(0, day_change)`: reduced expectations can lower the loss but
    the day is capped at neutral, so a retroactive reclassification can **never** produce a
    win (`test_retroactive_mode_only_when_paid_and_never_a_win`).
- **Retroactive mode is allowed ONLY via a paid mulligan.** `POST /day-assignments` still
  409s a direct past-day application; the mulligan endpoint is the paid gate that creates
  the `is_retroactive` assignment.
- **Cost ladder + cap enforced server-side** (`forgiveness.mulligan_cost`): 200/400/800 by
  the Nth mulligan; **cap 3/month**, counted by the **mulliganed day's calendar month**
  (decision — §8.3 says "3/month"); the 4th → 409. Not just client-side.
- **XP split — lifetime vs spendable** (resolves §8's "permanent AND spendable"): *lifetime
  earned* is permanent, drives account level, and is **never lowered by spending**;
  *spendable* = earned − Σ mulligan costs. `account_level` comes from lifetime; affordability
  checks spendable; insufficient → 409. `xp_lifetime` = latest day-close ledger balance;
  `xp_spent` = Σ `mulligans.xp_cost` (so wiping the ledger can't lose the spend record).
- **Past-day only:** `effective_day >= today` → 422 (apply a mode for free instead). "Today"
  is the same `get_today` dependency (pinned per test).
- **Propagation:** spending re-closes the latest scored day so the forgiveness flows into
  `rank_state`. `day_evaluations` stay the *raw* per-day record; `rank_state`/XP reflect
  forgiveness; the authoritative recompute is always the replay from source.
- **Tests:** 6 new (`test_mulligan_api.py`) — neutralize a losing day, monthly-cap blocks
  the 4th, retroactive-mode-only-when-paid + never-a-win, insufficient XP, today/future
  rejected, cache-wipe recompute. **76 tests total green.**

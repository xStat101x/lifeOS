# LifeOS — Full Technical Specification (v1)

> **Working name:** "LifeOS" is a placeholder — rename freely.
> **Status:** Design-complete draft for build. Every major decision below is intentional and resolved. Values marked **TUNABLE** ship with a concrete default so you can implement immediately; the owner will adjust by feel. Season 1 is explicitly a calibration period for the scoring constants.

---

## 0. How to use this document (read first, Claude Code)

This is a decision-complete spec from a long design conversation. You should **not need to guess** on architecture or mechanics. Where you hit an underspecified detail, prefer a small, reversible, well-commented choice and record it in `DECISIONS.md` rather than inventing a large subsystem.

Three hard rules for this build:

1. **Do not hardcode external identifiers that drift** — LLM model strings, the current-year IRS Roth contribution limit, Apple entitlement names, Actual Budget / SimpleFIN API endpoints. Read them from live docs at build time or from one `config.py` / `.env`. See §24.
2. **The phone is autonomous; the server is canonical.** Daily logging and scoring must work with the server unreachable (see §4, §20). When the phone reconnects, the **server's recomputation is authoritative**.
3. **Rank rises only from doing the thing.** No mechanic (Day Mode, mulligan, reward) may convert a miss into a *win* — only into *neutral* or a *reduced expectation*. This invariant protects the entire progression system.

---

## 1. Project overview

LifeOS is a single-user, local-first "life operating system": a unified tracker for **habits, systems (routines), fitness, nutrition, sleep, calendar, and personal finance**, wrapped in a **competitive ranking system** modeled on esports ladders (League-style LP with Iron→Challenger tiers and seasonal resets).

The owner has ADHD. The product exists to convert scattered goals into a system that is (a) frictionless enough to use daily, (b) rewarding enough to keep using until it's habitual, and (c) honest enough that the rank means something. Near-term goal: a muscle/weight **gain (bulk)** phase over the summer, expanding into full life management before a demanding senior year.

Long-term: open-source as a portfolio piece, then possibly productize. **Build v1 for one user.** No multi-tenancy or SaaS scaffolding now — but keep a `user_id` column on core tables so future multi-user isn't a rewrite.

---

## 2. Design principles

- **ADHD-first.** Kill capture friction. Reward showing up. Never punish rest. No hard streak resets — a single bad day must never wipe progress. Reliable notifications are the retention engine.
- **Local-first & private.** Finance and health data live on the owner's hardware. No public internet exposure (owner is a cybersecurity student — treat secrets, network surface, and data-at-rest accordingly, §21).
- **The one unavoidable manual action is food logging** — make it near-instant and make the app *learn* so it gets faster.
- **Delegate solved problems** — Actual Budget for finance, Apple Watch/HealthKit for sleep/fitness sensing.
- **Deterministic scoring** — scores are a pure function of logged events + config, so any node computes the same result once synced.

---

## 3. Non-goals / out of scope for v1

- Google Calendar / Microsoft Teams connectors — owner funnels both into Apple Calendar; LifeOS reads **Apple Calendar only** (§16).
- Plaid — finance uses Actual Budget + SimpleFIN (§17).
- Local-GPU vision — the server has no suitable GPU; the food agent calls a hosted API (§14).
- Multi-user, auth/login, sharing, billing.
- A heavy todo/project manager — a minimal, **non-auto-scheduled** task list is optional and low priority (§16).
- A lifting *progression engine* (auto-adding weight) — plans are explicit and imported; the app only *flags* when you're beating targets (§13).
- Android. iOS + web dashboard only.

---

## 4. System architecture

Three components, one API.

### 4.1 iOS app — primary client
- Native **Swift / SwiftUI**. Requires a paid Apple Developer account ($99/yr — accepted).
- **Fully offline-capable, local-first.** Owns an on-device DB + sync queue; runs **indefinitely** with the server unreachable — all daily capture and all scoring work offline.
- Native is required (not optional) for **HealthKit** (sleep, cardio, workouts, body weight), **EventKit** (read Apple Calendar, write LifeOS blocks), and **reliable push notifications**.
- **The scoring engine runs on the phone** at day-close (§10), so ranks compute offline.

### 4.2 Server (the "Dell box") — canonical hub, home-lab
Runs on the owner's home server, intended as an always-on home-lab reachable from any device. Responsibilities: canonical merged datastore and **authoritative scoring recomputation**; the **food agent**; the **finance engine** (Actual + SimpleFIN); the **web dashboard** API + hosting; scheduled jobs (nightly bank pull, weekly report, backups).

If the server is down the owner loses *convenience* (fresh bank data, food-photo processing, the dashboard) but **never data, logging ability, or rank**. Physical location for the fall is undecided and does not affect correctness.

### 4.3 Web dashboard — desk-work client
- **React PWA** served by the server; runs on the Windows gaming PC and gaming laptop.
- Where "sit down and think" work happens: finance review, editing/importing lifting plans, weekly analysis, configuring habits and Day Modes. Daily *capture* is on the phone; deep *review* is here.

### 4.4 Redundancy hierarchy
**Server = canonical source of truth. Windows PC = backup node (replica/restore target). Phone = offline-first cache.** The phone computes provisionally offline and accepts the server's canonical recompute on sync (§20).

### 4.5 Networking
- **Tailscale** private mesh between phone, server, desk machines. **Nothing exposed to the public internet**; no inbound ports for v1.

### 4.6 Food agent reachability
The food agent lives **only on the server**. When the server is unreachable the phone **queues the photo + note** and shows "pending estimate," reconciling on return. No on-phone vision fallback — the only realistic "down" state is the phone lacking Wi-Fi, where real-time macros aren't needed.

---

## 5. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| iOS client | Swift / SwiftUI + **GRDB (SQLite)** | Shared, deterministic SQLite schema with the server. |
| Server API | **Python + FastAPI** | Owner knows Python. |
| Server DB | **PostgreSQL** | Canonical datastore. |
| Web dashboard | **React (PWA)** | Served by the box. |
| Networking | **Tailscale** | Private mesh. |
| Finance | **Actual Budget** (self-hosted) + **SimpleFIN Bridge** (~$15/yr) | Pull via `actualpy`. |
| Food vision | **Claude (Sonnet-tier) via Anthropic API** | Current model string from docs at build time; tiered so known meals cost nothing (§14). |
| Voice note | On-device iOS speech-to-text | Food descriptions when a photo isn't enough. |

---

## 6. Data model

Postgres is canonical; the iOS SQLite store mirrors the offline subset. **Client-generated UUID** primary keys so offline rows never collide. Store UTC `logged_at` plus an explicit `effective_day` (local logical day, §10). Flexible config in `jsonb`. Add `created_at`/`updated_at`/`deleted_at` (soft-delete) to every table for sync.

### 6.1 Identity & taxonomy
```
users(id, display_name, created_at)                  -- single row in v1
domains(id, key, name, weight)                        -- Nutrition, Fitness, Sleep, Routines, Finance
```

### 6.2 Habits & systems
```
habits(
  id, user_id, domain_id, name,
  kind,                    -- 'binary' | 'quantitative'
  importance,              -- 1..5, owner-set; drives LP magnitude + rollup weight
  schedule_type,           -- 'weekdays' | 'daily' | 'specific_days' | 'floating_count'
  schedule_config jsonb,
  timing_window jsonb,     -- optional {start,end}; null = no timing component
  is_lifelong bool, active bool
)
habit_phases(              -- time-versioned targets (bulk/maintain/cut, etc.)
  id, habit_id, name, target_value, target_unit,
  effective_from, effective_to     -- to=null means current
)
systems(
  id, user_id, domain_id, name, importance,
  expected_duration_min, timing_window jsonb, active
)
system_steps(id, system_id, position, habit_id, inline_label)
```
> Note: "relaxed weekends" is **not** a habit flag — it's expressed via Day Modes (§9). Targets and timing for any given day are resolved as *phase target × active Day Mode overrides*.

### 6.3 Logs (source of truth)
Append-only; everything derivable is derived from here.
```
logs(id, user_id, target_kind, target_id, value, unit, logged_at, effective_day, source, meta jsonb)
  -- target_kind: 'habit'|'system_step'|'system'
  -- source: 'manual'|'photo'|'voice'|'watch'|'import'|'actual'|'system'
```

### 6.4 Day Modes (§9)
```
day_modes(id, name, description, is_seed bool)
day_mode_overrides(
  id, day_mode_id, scope,       -- 'domain' | 'habit' | 'system'
  scope_id,
  op,                            -- 'pause' | 'scale_target' | 'neutralize_timing' | 'expect_more' | 'scale_importance'
  factor,                        -- e.g. 0.6 for scale_target; null for pause/neutralize
  params jsonb
)
day_mode_reminders(id, day_mode_id, text, at_time, relative_to)   -- e.g. "eat before you compete"
day_assignments(
  id, effective_day, day_mode_id,
  source,                        -- 'scheduled' | 'calendar_suggested' | 'manual'
  is_retroactive bool, mulligan_id, applied_at
)
```

### 6.5 Scoring, seasons, currencies
```
seasons(id, name, start_day, end_day, reset_compression)          -- configurable; first starts 2026-08-20
rank_peaks(id, season_id, scope, scope_id, peak_lp, peak_tier, peak_division)
day_evaluations(                                                  -- one row per (scored target, effective_day)
  id, effective_day, target_kind, target_id, domain_id,
  completion, completion_baseline, timing, timing_baseline,
  performance_score, gain, decay, lp_change,
  applied_mode_id, was_paused, computed_at
)
rank_state(id, scope, scope_id, season_id, lp, tier, division, updated_at)   -- scope: 'habit'|'domain'|'overall'
xp_ledger(id, event, xp_delta, balance, effective_day, created_at)           -- XP is PERMANENT; never season-resets
account_level(id, level, xp_into_level, updated_at)
rewards(id, name, cost_type, cost, unlocked_at, redeemed_at)                 -- cost_type: 'xp'|'level_milestone'
mulligans(id, effective_day, target_kind, target_id, xp_cost, created_at)
```

### 6.6 Fitness
```
exercises(id, name, modality, primary_muscles jsonb, secondary_muscles jsonb, default_unit)  -- modality: 'lift'|'cardio'
lift_plans(id, source_json jsonb, imported_at, effective_from, active)
lift_plan_entries(
  id, plan_id, scheduled_date, day_pattern, exercise_id,
  target_sets, target_reps, target_weight, is_lite, bonus_eligible
)
lift_sets(id, exercise_id, effective_day, set_number, weight, reps, source, is_adhoc)   -- is_adhoc: unscheduled/bonus
cardio_sessions(id, exercise_id, effective_day, distance, duration_min, avg_hr, source)  -- 'watch'
```
> **Ad-hoc lifting** (§13) simply writes `lift_sets` with no matching plan entry and `is_adhoc = true`.

### 6.7 Body metrics
```
weight_entries(id, effective_day, weight, unit, source, trend_value)   -- trend_value = smoothed (§15)
```

### 6.8 Nutrition
```
meals(id, logged_at, effective_day, calories, protein, description, photo_ref, source, template_id, confidence, confirmed)
meal_templates(id, name, calories, protein, learned_from_meal_id, tap_count, last_used)   -- meal memory
```

### 6.9 Calendar & tasks
```
calendar_cache(id, external_event_id, title, start, end, source_calendar, all_day)   -- read-only mirror (EventKit)
lifeos_blocks(id, system_id, effective_day, start, end, external_event_id)           -- blocks LifeOS created
tasks(id, title, notes, due_day, done, created_at)                                   -- OPTIONAL, minimal, never auto-scheduled
```

### 6.10 Finance (thin cache over Actual)
```
fin_transactions(id, actual_id, date, amount, merchant, category, account, pending)
fin_budgets(category, period, limit_amount)     -- includes discretionary "fun money" (§17)
fin_snapshots(id, date, net_worth, cash, by_category jsonb)
```

---

## 7. Scoring & progression (the core)

### 7.1 Philosophy: rank is an equilibrium, not a running total
Naive "did it → +LP" saturates at Challenger the moment you're consistent — which is the goal — so it stops meaning anything. Pure baseline-relative scoring has the opposite flaw: perfect consistency yields zero improvement, so decay erodes you for *succeeding*. The resolution:

**Each day, LP changes by `gain − decay`, where decay scales with how high your rank already is.** Your rank settles at the equilibrium where your performance-driven gain equals rank-proportional decay. This gives all four desired behaviors:
- **Sustained excellence → a stable high rank.** The reward is *holding* it; holding takes ongoing effort because decay always pulls. No meaningless ceiling.
- **Genuine improvement → climbing.** Beating your recent baseline adds gain, raising your equilibrium.
- **A slump → sliding, then self-correcting** as the baseline falls.
- **Your equilibrium rank ≈ your current discipline level.**

### 7.2 Per-habit daily performance score (at day-close, §10)
For each habit scheduled on `effective_day`, after applying the day's active Day Mode (§9):
```
target      = active_phase_target × (product of scale_target overrides from the active mode)
completion  = clamp(actual / target, 0, COMPLETION_CAP)      -- binary habits: 1 if logged else 0
                                                             -- COMPLETION_CAP = 1.25 (TUNABLE)
baseline    = mean(completion over last BASELINE_WINDOW eligible days)   -- BASELINE_WINDOW = 14 (TUNABLE)
              -- excludes paused days (mode-paused or Away); new habits (< 7 days) use a low anchor so
              -- early completions are strong wins and early misses cost nothing

absolute_term    = completion - PASS_LINE     -- PASS_LINE = 0.5 (TUNABLE). Hitting target (1.0) → +0.5;
                                              -- missing entirely (0) → −0.5; half → 0. This is what lets
                                              -- consistency stay net-positive against decay.
improvement_term = completion - baseline      -- beating your recent self → +
timing_term      = (timing - timing_baseline) -- 0/1 in-window vs baseline; ZEROED when the active mode
                                              -- neutralizes timing, or when the habit has no timing_window

performance_score = W_ABS*absolute_term + W_IMP*improvement_term + W_TIMING_eff*timing_term
   W_ABS = 0.5, W_IMP = 0.35, W_TIMING = 0.15   (TUNABLE; W_TIMING_eff = 0 when neutralized)

importance_mult = importance / 3              -- maps 1..5 → 0.33..1.67 (TUNABLE)
gain = BASE_LP_SWING × importance_mult × performance_score      -- BASE_LP_SWING = 15 (TUNABLE)
       -- new-habit grace (< 7 days): clamp gain = max(0, gain) so early days can only help, never hurt
       -- (otherwise the absolute_term would still penalize an early miss, contradicting the grace intent)
```
Magnitude falls out naturally: a big overachievement (large positive `completion − baseline` and `− PASS_LINE`) yields a big gain; a bad miss on an important habit yields a big loss — exactly the "win well / lose bad harder" behavior.

**Paused** habits (mode or Away) are skipped entirely: no evaluation, no baseline contribution, no gain, no decay.

### 7.3 LP update with rank-proportional decay
The gain−decay recurrence runs **at the domain level** — that's where the equilibrium lives. Sum the day's member-habit/system gains into `gain_total` for the domain, then:
```
decay = DECAY_RATE × max(0, current_lp − FLOOR)      -- DECAY_RATE = 0.02, FLOOR = 0 (TUNABLE)
lp    = max(FLOOR, current_lp + gain_total − decay)
```
Equilibrium sits where `gain_total = decay`. Higher performance → higher equilibrium. Decay is **suspended for a domain on any day where all of its scheduled expectations are paused** (Away, Travel, Vacation, severe Sick, etc.) so legitimate rest — not just formal "Away" — is never punished.

### 7.4 Systems (routines)
System completion = `steps_done / steps_total` (0..1), evaluated exactly like a quantitative habit against its own baseline, using the system's `timing_window` and the active mode. **Completion is judged by the checklist, not the clock** — running over the time block is fine (§16).

### 7.5 Expected vs. bonus (applies app-wide)
> **Expected work protects rank and earns normal credit. Anything beyond what's scheduled earns bonus XP and is never required.**

So: nothing scheduled → neutral, no penalty; a lighter scheduled day → a lite session is full completion of that lighter target; **unscheduled** training or exceeding a target beyond `COMPLETION_CAP` → **bonus XP** ("overtime / S-rank" flair), never a raised baseline.

### 7.6 Aggregation
- **Domain LP** = the replayed gain−decay recurrence (§7.3) over all days — deterministic and re-computable from `day_evaluations`. **Decay applies only at the domain level**, never double-counted at habit or overall scope.
- **Overall LP** = `Σ(domain_lp × domain.weight) / Σ(domain.weight)` — a derived weighted average of domain LPs, with no separate accumulator or decay of its own.
- **Habit-level rank**, if surfaced, is a derived drill-down view (completion / e1RM trend), not an independent decaying ladder.
- The owner primarily watches **per-domain ranks** (Nutrition, Fitness, Sleep, Routines, Finance) plus overall.

### 7.7 Tier ladder
```
Iron, Bronze, Silver, Gold, Platinum, Emerald, Diamond   -- 4 divisions each, LP_PER_DIVISION = 100 (TUNABLE)
Master, Grandmaster, Challenger                           -- apex; single-player → fixed LP thresholds
```
Surface promotions/demotions with celebration/warning moments — a primary dopamine surface.

### 7.8 Seasons & soft reset
- **Seasons are quarterly by default and user-adjustable** (start dates are configurable anchors). **First season starts 2026-08-20** (back-to-school). *Do not* start on 2026-08-01 (owner's 21st birthday week).
- At season rollover, ranks **soft-reset** by compressing toward the ladder midpoint:
  ```
  new_lp = MIDPOINT + (old_lp − MIDPOINT) × reset_compression      -- reset_compression ≈ 0.35 (TUNABLE)
  ```
  A Diamond drops to roughly Gold and re-climbs — **not** a reset to zero.
- **Calibration target (owner's spec):** tune `reset_compression` + `DECAY_RATE` so that **a perfect month (~30 days) reclaims your previous peak**, leaving the remaining two months to push beyond. Realistic (imperfect) play should reclaim peak around month two. **Surpassing your previous peak requires genuinely improved performance** (a higher equilibrium) — that's intended. Season 1 is a calibration run; expect to adjust these two constants after living through one reset.
- **Previous peak is banked** in `rank_peaks` and shown on the profile ("Season 1 peak: Diamond II"). Progress is preserved as a record, not erased.
- **XP and account level never reset.** Rank = volatile seasonal ladder; XP/level = permanent lifetime progression. This is why the two currencies are separate.

---

## 8. XP, rewards, and forgiveness

Two deliberately separate currencies:
- **Rank** — quality & consistency. Volatile, per-domain, seasonal. **Rises only by doing the thing.**
- **XP** — participation. Earned for *showing up at all*, so even a net-negative rank day yields progress. Drives account level. Permanent. Spendable.

### 8.1 XP earning
- Any qualifying log grants base XP (`XP_PER_LOG = 10`, **TUNABLE**).
- Exceeding targets / unscheduled (bonus-eligible) work grants extra XP.
- XP is never reduced by a bad day.

### 8.2 Levels & rewards
- Increasing level thresholds (**TUNABLE** table).
- **Every 10 levels unlocks a reward token** the owner defines (cheat day, ice cream, a vacation-fund tick). Unlock is automatic; redeem is manual.

### 8.3 Forgiveness (two real-life events)
**Planned adjustment → free, via Day Modes (§9).** Scheduling a mode for today or the future (travel, vacation, competition, sick, going out) honestly reshapes expectations — reduced targets, pauses, neutralized timing. This is accounting, not cheating, so it's free.

**Unplanned retroactive erase → XP-purchased mulligan.** To reclassify a *past* day that already scored badly (genuinely forgot, life detonated), spend a **mulligan**: it either converts that day's loss to neutral or applies a Day Mode retroactively. Capped at `MULLIGAN_CAP = 3/month` (**TUNABLE**) with escalating cost (e.g., 200 → 400 → 800 XP).

**Invariant:** neither can produce a *win* — only neutral / reduced expectation. Otherwise rank becomes pay-to-win and dies.

---

## 9. Day Modes

A **Day Mode** is a named, reusable template that reshapes a day's expectations. The owner keeps a small editable library; each mode adjusts each domain/habit/system with these primitives:

- **Pause** — no expectation; excluded from baseline and decay.
- **Scale target** — multiply the target (e.g., protein ×0.6); you still *earn* for hitting the adjusted bar.
- **Neutralize timing** — drop the timing component (sleep/eat whenever).
- **Expect more** — raise the bar / flag bonus-eligible for a day of extra effort.
- **Scale importance** — raise/lower a habit's weight for that day (optional; e.g., sleep the night before a competition).

Modes may also carry **reminders** (e.g., "eat before you compete") — not just scoring changes.

### 9.1 Scheduling & anti-exploit
- Applying a mode to **today or the future is free** (honest planning — you know Friday is travel).
- Reclassifying a **past** day that already scored badly **costs a mulligan** (§8.3) — you cannot cost-free erase a real miss.
- Because it reads your calendar, LifeOS may **suggest** a mode ("flight detected Friday — apply Travel mode?").

### 9.2 Baseline integration
Completion is always `actual / target-for-that-day`, so a Travel day where you hit a reduced protein target counts as "met expectations" (completion ≈ 1.0) and does **not** corrupt your normal-day baseline. Paused habits are simply excluded.

### 9.3 Seed mode library (editable — see §22)
- **Weekday** (default) — full structure.
- **Weekend** — neutralize timing on schedule-flexible habits (morning routine, wake time); **nutrition stays full weight** (protein still matters on weekends); lifting typically not scheduled Sat/Sun per the plan.
- **Travel** — Fitness *paused*; protein *scaled ×0.6*; sleep *timing-neutralized*.
- **Vacation** — nothing paused (still earn if you train); food target relaxed / over-target not penalized (fine on a bulk); sleep *timing-neutralized*.
- **Competition** *(gymnastics; refine closer to late-winter season)* — no scheduled lift (the comp is the training; taper/rest around it lives in the plan); nutrition *neutralized* except a **"eat before you compete" reminder**; optional *scale_importance* up on sleep the night before.
- **Sick** — severity toggle: mild → *scale* targets down; severe → *pause*.
- **Going Out** — sleep *timing-neutralized* (late night); nutrition tolerance widened (drink calories logged but not penalized); daytime untouched.

---

## 10. Day-close & sleep handling

The logical day does **not** roll at midnight (night owl; a 1am toothbrush must count for the right day).

- **Day-close is primarily manual, then sensor-backed.** Real workflow: after the bedtime routine (before pre-sleep gaming), tap **"close my day"** → finalizes and scores on-device. If forgotten, **Apple Watch sleep detection auto-closes** as a fallback; failing that a hard cutoff (`HARD_DAY_CUTOFF = 06:00 local`, **TUNABLE**, night-owl-friendly) closes it. The flaky sensor is the *backup*, not the trigger.
- **Day-close is provisional and non-destructively re-scorable.** Late sleep data, a reclassified nap, or a corrected log silently **re-scores** the day. Nothing finalizes irreversibly. Closing **scores** the day now but does not **lock** it — a late log (an 11:30pm snack after you "closed") still lands on the current logical day and re-scores it, until real sleep or the hard cutoff actually ends the day.
- **`effective_day`** buckets every log/eval; a 1:30am pre-sleep log belongs to the previous logical day.
- **Naps** excluded via duration + time-of-day heuristic, with a manual **"that was a nap"** override.
- **Slept-in / all-nighter / sleep-at-2pm** all resolve through manual-primary + sleep-backup + hard-cutoff.

---

## 11. Habits & systems — behavior

- A **habit** is atomic and recurring; a **system** is an ordered set of steps (habits or inline items). Morning routine is the flagship system and first use case.
- **Lifelong** habits/systems (`is_lifelong`) have no "done" (working out, brushing teeth); others map to goals with targets/deadlines.
- **Phases** switch nutrition bulk → maintain → cut over time; targets are **time-versioned**, so historical days are judged against the target active *then* — switching to a cut never retroactively fails your best bulk weeks.
- **Schedules:** `weekdays`, `daily`, `specific_days`, `floating_count` (e.g., "3×/week, any days" — due until the weekly count is met; the week's shortfall is what's scored).
- **Importance (1–5)** scales LP magnitude and rollup weight; a Day Mode can temporarily scale it.

---

## 13. Fitness subsystem

**Fast set entry (scheduled days):** for the day's planned lifts (pre-loaded from the active plan), rapidly enter weight × reps per set ("bam, bam, bam"); one `lift_sets` row per set. **Log what you actually did** — actuals may exceed plan targets, and should.

**Ad-hoc workout logging (unscheduled / bonus days):** a quick flow to **search the exercise catalog, add lifts on the fly, and log sets** when nothing is scheduled (e.g., you decide to train on an off day, or add work on a Vacation day). Writes `lift_sets` with `is_adhoc = true` → earns **bonus XP** per §7.5. Cardio on such days pulls from Apple Watch automatically.

**Plan import (JSON):** design a program conversationally with AI → export JSON → import.
- Explicit **dated or day-patterned schedule** (no progression engine). Each entry pre-loads a day's exercises so logging is just entering actuals.
- **Preview-before-apply:** parse, validate against the catalog, show a diff, then commit. A malformed export must never silently corrupt the program.
- **No upload = no change** — the current plan continues.
- Unknown exercises → prompt to create catalog entries (with muscle tags) so IDs stay stable and aggregation is consistent.
- Sample format:
```json
{
  "effective_from": "2026-07-07",
  "entries": [
    { "day_pattern": "MO", "exercise": "Barbell Back Squat", "modality": "lift",
      "primary_muscles": ["quads","glutes"], "secondary_muscles": ["hamstrings","core"],
      "target_sets": 4, "target_reps": 6, "target_weight": 225, "is_lite": false, "bonus_eligible": true }
  ]
}
```

**Progress measurement — estimated 1-rep-max (e1RM) as the default strength trend.** e1RM converts any set (e.g., 185×8) into an estimated max single via a standard formula (Epley/Brzycki), so days of heavy 6s and lighter 12s compare on **one line**. This *is* the "am I getting stronger on this exercise / muscle" view; raw weight and reps are shown too. Because you log **actuals**, doing 185×14 when the plan said 185×12 raises your e1RM (correctly reflecting the extra strength) **and** earns a win + bonus. When you **consistently beat a target**, the app flags it as your cue to **bump the plan** on your next import — progressive overload without an auto-progression engine.

**Drill-down:** exercise → muscle region (legs/upper/etc.) via primary/secondary tags → modality → domain, so you can view a single lift, a muscle region, cardio, or the Fitness domain, seeing weight/reps/e1RM/distance trends improve.

---

## 14. Nutrition subsystem & food agent

For a bulk, track **two numbers: total calories and protein** (full macros are unnecessary friction).

**Capture paths (all fast):**
- **Photo → server agent → estimate** (calories + protein + confidence; low confidence prompts a quick confirm/correct).
- **Voice/manual** when a photo isn't possible ("beer at the bar," "late-night food truck") — speech-to-text → estimate or direct entry.
- **Modifier notes** ("swapped regular PB for protein PB") — optional photo + short (voice) description adjusts the estimate.
- **One-tap re-log** from meal memory, **with a fast portion adjust ("same / bigger / smaller," or a ×0.5–×2 stepper)** that scales the template's calories/protein — one tap must not lie about portion, which for a bulk is the number that matters.

**Meal memory:** on confirm/correct, upsert a `meal_templates` row. Recognized recurring meals (the daily shake) become one-tap entries with **no API call**; only genuinely novel food hits the vision model.

**Model tiering (cost control):** known meal / re-log → **no API**; simple/seen-similar → cheapest capable model; genuinely novel plate → Sonnet-tier vision. Realistic cost: cents/day, falling as memory grows. **Pull the current model string from Anthropic docs at build time.**

**Offline:** photos queue on the phone and process on reconnect (§4.6).

---

## 15. Body metrics

- **Weight** from a smart scale via Apple Health. Store raw plus a **smoothed `trend_value`** (`WEIGHT_SMOOTHING = 7-day EMA`, **TUNABLE**). Daily scale weight is water-noise; for a bulk the **trend line** is what matters and what the UI emphasizes.

---

## 16. Calendar subsystem

**Apple Calendar only (v1).** The owner routes Teams + Google into Apple Calendar, so LifeOS reads that single aggregated source via **EventKit** — no Google/Teams connectors.
- **Read** all aggregated calendars **read-only**.
- **Write** auto-blocks to a **dedicated LifeOS calendar it owns** — never touch the owner's other calendars.
- **Auto time-blocking applies to systems/routines only — never ad-hoc todos** (respecting the owner's "later = more urgency" rule).
- Blocks are **soft containers + notification anchors**; completion is by **checklist, not clock** — running over when nothing follows is fine.
- **Tasks (optional, low priority):** a minimal in-app list, **never auto-scheduled**. Keep it tiny.

---

## 17. Finance subsystem

**Delegate the engine to self-hosted Actual Budget** (auto bank-sync, categorization, envelope budgeting); LifeOS pulls via `actualpy`. Bank sync via **SimpleFIN Bridge (~$15/yr)** — chosen over Plaid (less code, no 10-account cap, cleaner privacy, no shifting dev tier). Daily refresh is sufficient.

**What LifeOS adds:**
- A **unified dashboard**: where money goes, by category, vs. budget, searchable for the owner's own insights.
- An **allocation waterfall** — model take-home through a *priority stack*, not essentials-vs-invest:
  1. **Essentials** (rent, food, utilities, minimum debt).
  2. **Emergency buffer** — toward N months of essentials (`BUFFER_MONTHS = 3–6`, **TUNABLE**) *before* aggressive investing.
  3. **Discretionary / fun money** — a **budgeted line item** (bars, going out), decided up front. First-class, not leftover.
  4. **Investing surplus** → Roth (to the annual cap) → taxable/other.
- **Roth-headroom = surplus *after* essentials + buffer + discretionary budget**, capped at the remaining annual Roth limit (**fetch the current-year IRS limit at build time**). Never recommends investing money earmarked for buffer or fun.
- **"Max the Roth *and* have fun money?"** — the dashboard shows the waterfall and **flags when maxing would starve the buffer or the fun budget.** Maxing is one priority in a stack, not a mandate.
- A **Finance rank** that rewards **staying within the budgets you set — including the fun-money budget** — not punishing discretionary spending itself. A bar night *within budget* is a **win**; blowing a budget you set is the miss.
- An **LLM auto-categorizer**. Categories have a **single master** (Actual or LifeOS owns assignment; the other is read-only) to avoid two-master drift.

Data flow: nightly server job pulls from Actual → refresh cache tables → recompute Finance rank at day-close. Because bank data lags (SimpleFIN refreshes ~daily and charges can post days late), **Finance evaluations are provisional** — a bar charge that posts two days late re-scores that day's Finance rank when it arrives (per §20's re-scorable model). Expect occasional retroactive finance adjustments; that's correct, not a bug.

---

## 18. Notifications

Native iOS push — **the retention engine**. Anchor to system time-blocks, unmet daily targets before day-close ("40g protein to go"), rank/decay warnings ("Fitness slipping"), and **Day-Mode reminders** ("eat before you compete"). Meaningful, not spammy — a muted user is a dead engine.

---

## 19. Weekly report (accountability)

A **weekly summary** (server job) designed to be **shared with the owner's girlfriend** as a deliberate **external accountability mechanism** (the owner responds to real consequences more than self-assigned ones). Contents: rank movements per domain, wins, honest misses, bulk progress (weight trend, protein adherence), finance-vs-budget. **Build early**, not last. Output as a shareable link (over Tailscale) or exportable image/PDF.

---

## 20. Sync & offline model

- **Event-sourced core.** `logs` append-only, client-UUIDs; server merges, last-write-wins on edits (UUID-deduped), soft-delete via `deleted_at`.
- **Deterministic scoring** — pure function of `logs` + config; any node agrees once synced.
- **Authority:** **server post-merge recomputation is canonical.** PC is a backup node; phone is an offline-first cache that computes provisionally offline (so nothing blocks at a bar with no signal) and **accepts the server's recompute on sync** — expect occasional small rank corrections; normal, not a bug.
- **Sync queue** on the phone holds unsent logs + pending photos; drains over Tailscale.
- **Conflict scope is tiny** (single user, mostly append-only) — keep merge logic simple and well-tested; no CRDT framework.

---

## 21. Security & privacy

- **No public internet exposure** — all traffic over Tailscale; no open inbound ports.
- **Secrets** (SimpleFIN token, Anthropic key, Actual creds, Apple keys) in `.env`/secrets store, **never committed**; ship `.env.example`.
- **Encrypt at rest** — Postgres volume + backups; enable Actual's end-to-end encryption.
- **Least privilege** per component; isolate the food agent and finance job.
- Scrub all real data/tokens before any open-source release.

---

## 22. Seed data (ships with the app, all editable)

So the app is usable after ~5 minutes, not 5 hours (avoiding the onboarding cliff). Everything below is a starting placeholder the owner edits/deletes.

**Domains:** Nutrition, Fitness, Sleep, Routines, Finance.

**Starter system — "Morning Routine"** (Routines, timing window ~06:00–10:00 weekday): steps → brush teeth, wash face, make bed, drink water, 10-minute day plan.

**Starter habits:**
- *Protein target* — Nutrition, quantitative, daily, **importance 5**, phase "Bulk" with a **placeholder target the owner sets** (protein target should be owner-configured; the app can suggest a bodyweight-based starting figure but the owner sets the number).
- *Calorie target* — Nutrition, quantitative, daily, importance 4, "Bulk" surplus placeholder (owner-set).
- *Workout* — Fitness, driven by the imported plan, importance 5.
- *Wake time* — Sleep, timing-based, importance 3 (timing neutralized on Weekend/Going Out/Travel modes).
- *Brush teeth (PM)* — Routines, binary, daily, importance 2.

**Starter lifting plan — 4-day Upper/Lower, weekends open** (placeholder to replace with an AI-designed plan; aligns with the Weekend mode leaving Sat/Sun unscheduled):
```json
{
  "effective_from": "2026-08-20",
  "entries": [
    { "day_pattern":"MO","exercise":"Barbell Bench Press","modality":"lift","primary_muscles":["chest"],"secondary_muscles":["triceps","front delts"],"target_sets":4,"target_reps":6,"target_weight":null,"is_lite":false,"bonus_eligible":true },
    { "day_pattern":"MO","exercise":"Barbell Row","modality":"lift","primary_muscles":["lats","upper back"],"secondary_muscles":["biceps"],"target_sets":4,"target_reps":8 },
    { "day_pattern":"MO","exercise":"Overhead Press","modality":"lift","primary_muscles":["front delts"],"secondary_muscles":["triceps"],"target_sets":3,"target_reps":8 },
    { "day_pattern":"MO","exercise":"Lat Pulldown","modality":"lift","primary_muscles":["lats"],"secondary_muscles":["biceps"],"target_sets":3,"target_reps":10 },
    { "day_pattern":"TU","exercise":"Barbell Back Squat","modality":"lift","primary_muscles":["quads","glutes"],"secondary_muscles":["hamstrings","core"],"target_sets":4,"target_reps":6 },
    { "day_pattern":"TU","exercise":"Romanian Deadlift","modality":"lift","primary_muscles":["hamstrings","glutes"],"secondary_muscles":["lower back"],"target_sets":3,"target_reps":8 },
    { "day_pattern":"TU","exercise":"Leg Press","modality":"lift","primary_muscles":["quads"],"secondary_muscles":["glutes"],"target_sets":3,"target_reps":10 },
    { "day_pattern":"TU","exercise":"Standing Calf Raise","modality":"lift","primary_muscles":["calves"],"secondary_muscles":[],"target_sets":4,"target_reps":12 },
    { "day_pattern":"TH","exercise":"Incline Dumbbell Press","modality":"lift","primary_muscles":["upper chest"],"secondary_muscles":["front delts","triceps"],"target_sets":4,"target_reps":8 },
    { "day_pattern":"TH","exercise":"Pull-up","modality":"lift","primary_muscles":["lats"],"secondary_muscles":["biceps"],"target_sets":4,"target_reps":8 },
    { "day_pattern":"TH","exercise":"Seated Cable Row","modality":"lift","primary_muscles":["mid back"],"secondary_muscles":["biceps"],"target_sets":3,"target_reps":10 },
    { "day_pattern":"TH","exercise":"Dumbbell Shoulder Press","modality":"lift","primary_muscles":["front delts"],"secondary_muscles":["triceps"],"target_sets":3,"target_reps":10 },
    { "day_pattern":"FR","exercise":"Deadlift","modality":"lift","primary_muscles":["posterior chain"],"secondary_muscles":["lats","traps"],"target_sets":3,"target_reps":5 },
    { "day_pattern":"FR","exercise":"Hack Squat","modality":"lift","primary_muscles":["quads"],"secondary_muscles":["glutes"],"target_sets":3,"target_reps":8 },
    { "day_pattern":"FR","exercise":"Walking Lunge","modality":"lift","primary_muscles":["quads","glutes"],"secondary_muscles":["hamstrings"],"target_sets":3,"target_reps":10 },
    { "day_pattern":"FR","exercise":"Seated Calf Raise","modality":"lift","primary_muscles":["calves"],"secondary_muscles":[],"target_sets":3,"target_reps":15 }
  ]
}
```
(`target_weight` left null so the owner sets working weights on first log; Wed/Sat/Sun unscheduled.)

**Starter Day Modes:** Weekday, Weekend, Travel, Vacation, Competition, Sick, Going Out (as specified in §9.3).

**Starter finance categories/budgets:** Essentials group + a **Discretionary/"Fun money"** budget line + a Savings/Investing bucket — placeholders for the owner to set amounts.

**Seasons:** Season 1 = 2026-08-20 → ~2026-11-20 (quarterly, adjustable).

---

## 23. Build sequence

The app *core* is largely one-shottable from this spec; the **integrations are the real work** (gated on out-of-band steps: Apple Developer enrollment, HealthKit entitlements, SimpleFIN account, tuning the food agent, standing up Postgres + Tailscale). Plan for those to consume real calendar time regardless of spec quality.

1. **Foundation + core loop.** Data model; FastAPI + Postgres; iOS shell with local store + sync queue; habit/system engine; **Morning Routine** seeded; **on-device scoring** (equilibrium model + seasons); XP; per-domain + overall ranks; **Day Modes**; mulligans; manual + photo food quick-log (agent may stub initially). → *usable tomorrow morning after ~5 min setup.*
2. **Gamification polish + body/fitness capture.** Tier UI, promotion/demotion moments, notifications; HealthKit (sleep-driven day-close, cardio, weight + smoothing); **fast lift entry + ad-hoc logging**; JSON plan import with preview; e1RM trends.
3. **Nutrition agent for real.** Server vision agent, model tiering, meal memory, voice notes.
4. **Finance.** Actual + SimpleFIN; transaction cache; allocation waterfall; Finance rank; Roth-headroom; auto-categorizer.
5. **Calendar + report + polish.** EventKit read; LifeOS-owned calendar auto-blocking for systems; **weekly girlfriend report**; web dashboard depth; backups hardened.

Native iOS work is deliberately early — sleep, cardio, calendar read, and reliable notifications all require it.

---

## 24. Verify-at-build-time checklist (do not hardcode)

- **LLM model string(s)** for the food agent — read from Anthropic docs; store in config.
- **Current-year IRS Roth IRA contribution limit** — for the headroom cap.
- **SimpleFIN Bridge** setup-token flow + `actualpy` API surface — confirm current methods.
- **Apple entitlements** — HealthKit (sleep, workouts, body mass, cardio), EventKit read+write, push; plus Apple Developer enrollment.
- **Actual Budget** self-host version + e2e-encryption enablement.
- **Tailscale ACLs** so only the owner's devices see the server.

---

## 25. Deferred decisions (safe to defer; log in DECISIONS.md)

- Exact tunable constants (`BASE_LP_SWING`, `PASS_LINE`, `DECAY_RATE`, `reset_compression`, weights, level curve) — ship defaults; **Season 1 is the calibration run.**
- **Competition mode** fine-tuning (gymnastics; late-winter) — taper/rest scheduling in the plan, during/pre-comp reminders.
- Final server-location/availability strategy for the fall.
- Todo depth — keep minimal unless requested.
- Whether any habit wants per-habit override of the global scoring weights.

---

*End of specification. Meant to be reviewed and stress-tested with the owner before handoff — an ambiguity caught here is far cheaper than a wrong guess in code.*

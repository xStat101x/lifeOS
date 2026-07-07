# Phase 1 kickoff — paste into Claude Code (first session)

Read `docs/SPEC.md` in full, then `CLAUDE.md`. We are building **Phase 1 from spec §23 only**: the backend data model and the scoring engine. Do NOT build the iOS app, the web dashboard, or any external integration (no API keys, no bank sync, no HealthKit) yet.

**Goal for this session:** a Python / FastAPI + PostgreSQL skeleton with the core data model and a fully unit-tested scoring engine that runs with zero external services and can be validated entirely on this machine.

Work in this order, and **pause for my review after each step**:

1. Propose the module structure and the database schema (from spec §6) as migrations. Wait for my OK before writing code.
2. Implement the data model + migrations. Add a seed script that loads the §22 seed data: the Morning Routine system, the core habits, the seven starter Day Modes, and the sample upper/lower lifting plan.
3. Implement the scoring engine exactly per spec §7–§9:
   - equilibrium model: `gain − rank-proportional decay`, run at the **domain** level;
   - completion / absolute / improvement / timing terms, with the completion/timing weights;
   - new-habit grace: `gain = max(0, gain)` during the grace window;
   - Day Mode overrides: pause / scale target / neutralize timing / expect more / scale importance;
   - forgiveness: free planned modes vs. XP-capped retroactive mulligan — **never converting a miss to a win**;
   - seasons: quarterly soft reset compressing toward the ladder midpoint, calibrated so a perfect ~30 days reclaims prior peak; XP/level never reset.
4. Write a test suite proving each behavior on synthetic logs, including: consistent performance settles at a **stable** rank (no saturation); genuine improvement climbs; a slump slides then self-corrects; a fully-paused domain-day neither gains nor decays; a retroactive mulligan turns a loss to neutral but never to a win; a season reset reclaims peak in ~30 perfect days. Include a small **simulation harness** I can run to feed day-by-day logs and print rank + XP over time.
5. Summarize what's built, what's stubbed, and any open questions in `DECISIONS.md`.

Treat all scoring constants (`BASE_LP_SWING`, `PASS_LINE`, `DECAY_RATE`, `reset_compression`, the weights) as tunable config seeded with the spec's defaults — Season 1 is the calibration run. Keep everything runnable and tested locally.

"""§22 seed data — makes the app usable after ~5 minutes, not 5 hours.

Everything here is an editable placeholder for the owner (spec §22). Loads:
- the 5 domains,
- the Morning Routine system + steps,
- the 5 starter habits (with the nutrition "Bulk" phase placeholders),
- the 7 starter Day Modes with their §9.3 overrides + reminders,
- the 4-day Upper/Lower lifting plan (exercises + plan entries),
- placeholder finance budgets, and Season 1.

Idempotent: re-running is a no-op once domains exist.

Where §9.3 describes a Day Mode's effect in prose, the concrete override op/factor
chosen here is documented in DECISIONS.md; the owner tunes by feel.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session

from app.models import (
    AccountLevel,
    DayMode,
    DayModeOverride,
    DayModeReminder,
    Domain,
    Exercise,
    FinBudget,
    Habit,
    HabitPhase,
    LiftPlan,
    LiftPlanEntry,
    Season,
    System,
    SystemStep,
    User,
)

# --- Starter lifting plan (spec §22) --------------------------------------------
LIFT_PLAN: dict = {
    "effective_from": "2026-08-20",
    "entries": [
        {"day_pattern": "MO", "exercise": "Barbell Bench Press", "modality": "lift", "primary_muscles": ["chest"], "secondary_muscles": ["triceps", "front delts"], "target_sets": 4, "target_reps": 6, "target_weight": None, "is_lite": False, "bonus_eligible": True},
        {"day_pattern": "MO", "exercise": "Barbell Row", "modality": "lift", "primary_muscles": ["lats", "upper back"], "secondary_muscles": ["biceps"], "target_sets": 4, "target_reps": 8},
        {"day_pattern": "MO", "exercise": "Overhead Press", "modality": "lift", "primary_muscles": ["front delts"], "secondary_muscles": ["triceps"], "target_sets": 3, "target_reps": 8},
        {"day_pattern": "MO", "exercise": "Lat Pulldown", "modality": "lift", "primary_muscles": ["lats"], "secondary_muscles": ["biceps"], "target_sets": 3, "target_reps": 10},
        {"day_pattern": "TU", "exercise": "Barbell Back Squat", "modality": "lift", "primary_muscles": ["quads", "glutes"], "secondary_muscles": ["hamstrings", "core"], "target_sets": 4, "target_reps": 6},
        {"day_pattern": "TU", "exercise": "Romanian Deadlift", "modality": "lift", "primary_muscles": ["hamstrings", "glutes"], "secondary_muscles": ["lower back"], "target_sets": 3, "target_reps": 8},
        {"day_pattern": "TU", "exercise": "Leg Press", "modality": "lift", "primary_muscles": ["quads"], "secondary_muscles": ["glutes"], "target_sets": 3, "target_reps": 10},
        {"day_pattern": "TU", "exercise": "Standing Calf Raise", "modality": "lift", "primary_muscles": ["calves"], "secondary_muscles": [], "target_sets": 4, "target_reps": 12},
        {"day_pattern": "TH", "exercise": "Incline Dumbbell Press", "modality": "lift", "primary_muscles": ["upper chest"], "secondary_muscles": ["front delts", "triceps"], "target_sets": 4, "target_reps": 8},
        {"day_pattern": "TH", "exercise": "Pull-up", "modality": "lift", "primary_muscles": ["lats"], "secondary_muscles": ["biceps"], "target_sets": 4, "target_reps": 8},
        {"day_pattern": "TH", "exercise": "Seated Cable Row", "modality": "lift", "primary_muscles": ["mid back"], "secondary_muscles": ["biceps"], "target_sets": 3, "target_reps": 10},
        {"day_pattern": "TH", "exercise": "Dumbbell Shoulder Press", "modality": "lift", "primary_muscles": ["front delts"], "secondary_muscles": ["triceps"], "target_sets": 3, "target_reps": 10},
        {"day_pattern": "FR", "exercise": "Deadlift", "modality": "lift", "primary_muscles": ["posterior chain"], "secondary_muscles": ["lats", "traps"], "target_sets": 3, "target_reps": 5},
        {"day_pattern": "FR", "exercise": "Hack Squat", "modality": "lift", "primary_muscles": ["quads"], "secondary_muscles": ["glutes"], "target_sets": 3, "target_reps": 8},
        {"day_pattern": "FR", "exercise": "Walking Lunge", "modality": "lift", "primary_muscles": ["quads", "glutes"], "secondary_muscles": ["hamstrings"], "target_sets": 3, "target_reps": 10},
        {"day_pattern": "FR", "exercise": "Seated Calf Raise", "modality": "lift", "primary_muscles": ["calves"], "secondary_muscles": [], "target_sets": 3, "target_reps": 15},
    ],
}


def already_seeded(session: Session) -> bool:
    return session.query(Domain).count() > 0


def seed(session: Session) -> None:
    if already_seeded(session):
        print("Seed skipped: domains already present.")
        return

    # --- User (single row in v1, §6.1) ---
    user = User(display_name="Owner")
    session.add(user)
    session.flush()

    # --- Domains (§22). weight=1.0 placeholders; owner tunes the rollup (§7.6). ---
    domains = {
        key: Domain(key=key, name=name, weight=1.0)
        for key, name in [
            ("nutrition", "Nutrition"),
            ("fitness", "Fitness"),
            ("sleep", "Sleep"),
            ("routines", "Routines"),
            ("finance", "Finance"),
        ]
    }
    session.add_all(domains.values())
    session.flush()

    # --- Starter habits (§22) ---
    protein = Habit(
        user_id=user.id, domain_id=domains["nutrition"].id, name="Protein target",
        kind="quantitative", importance=5, schedule_type="daily", schedule_config={},
        timing_window=None, is_lifelong=True, active=True,
    )
    calories = Habit(
        user_id=user.id, domain_id=domains["nutrition"].id, name="Calorie target",
        kind="quantitative", importance=4, schedule_type="daily", schedule_config={},
        timing_window=None, is_lifelong=True, active=True,
    )
    workout = Habit(
        user_id=user.id, domain_id=domains["fitness"].id, name="Workout",
        kind="binary", importance=5, schedule_type="specific_days",
        schedule_config={"days": ["MO", "TU", "TH", "FR"]},  # matches the seed plan
        timing_window=None, is_lifelong=True, active=True,
    )
    wake_time = Habit(
        user_id=user.id, domain_id=domains["sleep"].id, name="Wake time",
        kind="binary", importance=3, schedule_type="daily", schedule_config={},
        timing_window={"start": "06:00", "end": "09:00"},  # neutralized on Weekend/Travel/Going Out
        is_lifelong=True, active=True,
    )
    brush_pm = Habit(
        user_id=user.id, domain_id=domains["routines"].id, name="Brush teeth (PM)",
        kind="binary", importance=2, schedule_type="daily", schedule_config={},
        timing_window=None, is_lifelong=True, active=True,
    )
    habits = [protein, calories, workout, wake_time, brush_pm]
    session.add_all(habits)
    session.flush()

    # Nutrition phases — placeholder Bulk targets; OWNER sets the real numbers (§22).
    session.add_all([
        HabitPhase(habit_id=protein.id, name="Bulk", target_value=160, target_unit="g",
                   effective_from=date(2026, 7, 7), effective_to=None),
        HabitPhase(habit_id=calories.id, name="Bulk", target_value=2800, target_unit="kcal",
                   effective_from=date(2026, 7, 7), effective_to=None),
    ])

    # --- Morning Routine system + inline steps (§22) ---
    morning = System(
        user_id=user.id, domain_id=domains["routines"].id, name="Morning Routine",
        importance=3, expected_duration_min=30,
        timing_window={"start": "06:00", "end": "10:00"}, active=True,
    )
    session.add(morning)
    session.flush()
    session.add_all([
        SystemStep(system_id=morning.id, position=i, habit_id=None, inline_label=label)
        for i, label in enumerate(
            ["Brush teeth", "Wash face", "Make bed", "Drink water", "10-minute day plan"]
        )
    ])

    # --- Day Modes (§9.3). See DECISIONS.md for the prose->override mapping. ---
    def mode(name: str, desc: str) -> DayMode:
        m = DayMode(name=name, description=desc, is_seed=True)
        session.add(m)
        session.flush()
        return m

    def ov(m: DayMode, scope: str, scope_id, op: str, factor=None, params=None) -> None:
        session.add(DayModeOverride(day_mode_id=m.id, scope=scope, scope_id=scope_id,
                                    op=op, factor=factor, params=params))

    # Weekday — default; full structure, no overrides.
    mode("Weekday", "Default — full structure.")

    # Weekend — neutralize timing on schedule-flexible habits; nutrition stays full.
    weekend = mode("Weekend", "Flexible timing; nutrition still full weight.")
    ov(weekend, "system", morning.id, "neutralize_timing")
    ov(weekend, "habit", wake_time.id, "neutralize_timing")

    # Travel — Fitness paused; protein x0.6; sleep timing-neutralized.
    travel = mode("Travel", "Fitness paused; protein x0.6; sleep timing-neutralized.")
    ov(travel, "domain", domains["fitness"].id, "pause")
    ov(travel, "habit", protein.id, "scale_target", factor=0.6)
    ov(travel, "domain", domains["sleep"].id, "neutralize_timing")

    # Vacation — nothing paused; food target relaxed; sleep timing-neutralized.
    vacation = mode("Vacation", "Nothing paused; food relaxed; sleep timing-neutralized.")
    ov(vacation, "domain", domains["nutrition"].id, "scale_target", factor=0.7)
    ov(vacation, "domain", domains["sleep"].id, "neutralize_timing")

    # Competition — no scheduled lift; nutrition neutralized (+ reminder); sleep importance up.
    comp = mode("Competition", "Comp is the training; eat before you compete; prioritize sleep.")
    ov(comp, "domain", domains["fitness"].id, "pause")
    ov(comp, "domain", domains["nutrition"].id, "pause")
    ov(comp, "habit", wake_time.id, "scale_importance", factor=1.5)
    session.add(DayModeReminder(day_mode_id=comp.id, text="Eat before you compete.",
                                at_time=None, relative_to="pre_event"))

    # Sick — severity toggle. Seed = mild (scale targets down); severe->pause is runtime.
    sick = mode("Sick", "Mild: targets scaled down. Severe: pause (runtime toggle).")
    ov(sick, "domain", domains["fitness"].id, "scale_target", factor=0.5,
       params={"severity": "mild"})
    ov(sick, "domain", domains["nutrition"].id, "scale_target", factor=0.5,
       params={"severity": "mild"})

    # Going Out — sleep timing-neutralized; nutrition tolerance widened; daytime untouched.
    going_out = mode("Going Out", "Late night: sleep timing-neutralized; drink cals not penalized.")
    ov(going_out, "domain", domains["sleep"].id, "neutralize_timing")
    ov(going_out, "domain", domains["nutrition"].id, "scale_importance", factor=0.6,
       params={"note": "drink calories logged but not penalized"})

    # --- Lifting plan: exercises (dedup by name) + plan + entries (§22) ---
    exercises: dict[str, Exercise] = {}
    for e in LIFT_PLAN["entries"]:
        if e["exercise"] not in exercises:
            ex = Exercise(
                name=e["exercise"], modality=e["modality"],
                primary_muscles=e.get("primary_muscles", []),
                secondary_muscles=e.get("secondary_muscles", []),
                default_unit="lb",
            )
            exercises[e["exercise"]] = ex
            session.add(ex)
    session.flush()

    plan = LiftPlan(
        source_json=LIFT_PLAN,
        imported_at=datetime.now(timezone.utc),
        effective_from=date.fromisoformat(LIFT_PLAN["effective_from"]),
        active=True,
    )
    session.add(plan)
    session.flush()
    for e in LIFT_PLAN["entries"]:
        session.add(LiftPlanEntry(
            plan_id=plan.id, scheduled_date=None, day_pattern=e["day_pattern"],
            exercise_id=exercises[e["exercise"]].id,
            target_sets=e.get("target_sets"), target_reps=e.get("target_reps"),
            target_weight=e.get("target_weight"),
            is_lite=e.get("is_lite", False), bonus_eligible=e.get("bonus_eligible", False),
        ))

    # --- Finance budgets — placeholders (§22); owner sets amounts (§17). ---
    session.add_all([
        FinBudget(category="Essentials", period="monthly", limit_amount=0.0),
        FinBudget(category="Fun Money", period="monthly", limit_amount=0.0),
        FinBudget(category="Savings/Investing", period="monthly", limit_amount=0.0),
    ])

    # --- Season 1 (§7.8, §22): 2026-08-20 -> ~2026-11-20, quarterly. ---
    session.add(Season(
        name="Season 1", start_day=date(2026, 8, 20), end_day=date(2026, 11, 20),
        reset_compression=0.35,
    ))

    # --- Account level starts at 1 (§8.2). ---
    session.add(AccountLevel(level=1, xp_into_level=0))

    session.commit()
    print("Seed complete.")

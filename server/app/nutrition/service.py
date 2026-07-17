"""Persist meals/templates and bridge meal macros into canonical habit logs."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import Domain, Habit, HabitPhase, Log, Meal, MealTemplate, User


class NutritionError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _target_active_on(habit: Habit, day: date) -> bool:
    if day < habit.created_at.date():
        return False
    inactive_from = None
    if habit.deleted_at is not None:
        inactive_from = habit.deleted_at.date()
    elif not habit.active:
        inactive_from = habit.updated_at.date()
    return inactive_from is None or day < inactive_from


def _nutrition_macro_targets(session: Session, day: date) -> dict[str, tuple[Habit, str]]:
    """Resolve protein/calorie targets from active phase units, never editable names."""
    rows = (
        session.query(Habit, HabitPhase)
        .join(Domain, Habit.domain_id == Domain.id)
        .join(HabitPhase, HabitPhase.habit_id == Habit.id)
        .filter(
            Domain.key == "nutrition",
            Domain.deleted_at.is_(None),
            Habit.kind == "quantitative",
            HabitPhase.deleted_at.is_(None),
            HabitPhase.effective_from <= day,
            (HabitPhase.effective_to.is_(None) | (HabitPhase.effective_to >= day)),
        )
        .all()
    )
    candidates: dict[str, list[tuple[Habit, str]]] = {"calories": [], "protein": []}
    for habit, phase in rows:
        if not _target_active_on(habit, day):
            continue
        unit = (phase.target_unit or "").strip().casefold()
        if unit in {"kcal", "calorie", "calories"}:
            candidates["calories"].append((habit, phase.target_unit or "kcal"))
        elif unit in {"g", "gram", "grams"}:
            candidates["protein"].append((habit, phase.target_unit or "g"))

    resolved: dict[str, tuple[Habit, str]] = {}
    for macro, matches in candidates.items():
        if len(matches) != 1:
            raise NutritionError(
                500,
                f"Nutrition config must resolve exactly one active {macro} target for "
                f"{day}; found {len(matches)}.",
            )
        resolved[macro] = matches[0]
    return resolved


def persist_meal(
    session: Session,
    *,
    meal_id: uuid.UUID | None,
    logged_at: datetime,
    effective_day: date,
    calories: float,
    protein: float,
    description: str | None,
    source: str,
    photo_ref: str | None = None,
    template_id: uuid.UUID | None = None,
    confidence: float | None = None,
    portion_multiplier: float = 1.0,
) -> tuple[Meal, bool]:
    """Write one meal plus its two scoring logs. Returns ``(meal, created)``.

    A client-supplied meal UUID makes offline retries idempotent: an existing meal does
    not emit duplicate protein/calorie logs or increment template memory twice.
    """
    if meal_id is not None:
        existing = session.get(Meal, meal_id)
        if existing is not None:
            if existing.deleted_at is not None:
                raise NutritionError(409, "meal id refers to a deleted meal")
            return existing, False

    user = session.query(User).first()
    if user is None:
        raise NutritionError(500, "No user seeded.")
    targets = _nutrition_macro_targets(session, effective_day)

    meal = Meal(
        id=meal_id or uuid.uuid4(),
        logged_at=logged_at,
        effective_day=effective_day,
        calories=calories,
        protein=protein,
        description=description,
        photo_ref=photo_ref,
        source=source,
        template_id=template_id,
        confidence=confidence,
        confirmed=True,
    )
    session.add(meal)

    log_source = source if source in {"manual", "photo", "voice"} else "manual"
    macro_values = {"calories": calories, "protein": protein}
    for macro, value in macro_values.items():
        habit, unit = targets[macro]
        session.add(Log(
            user_id=user.id,
            target_kind="habit",
            target_id=habit.id,
            value=value,
            unit=unit,
            logged_at=logged_at,
            effective_day=effective_day,
            source=log_source,
            meta={
                "meal_id": str(meal.id),
                "macro": macro,
                "capture_source": source,
                "template_id": str(template_id) if template_id else None,
                "portion_multiplier": portion_multiplier,
            },
        ))
    return meal, True


def persist_template(
    session: Session,
    *,
    template_id: uuid.UUID | None,
    name: str,
    calories: float,
    protein: float,
) -> tuple[MealTemplate, bool]:
    if template_id is not None:
        existing = session.get(MealTemplate, template_id)
        if existing is not None:
            if existing.deleted_at is not None:
                raise NutritionError(409, "template id refers to a deleted template")
            return existing, False
    row = MealTemplate(
        id=template_id or uuid.uuid4(),
        name=name,
        calories=calories,
        protein=protein,
        tap_count=0,
    )
    session.add(row)
    return row, True

"""Synthetic worlds + day generators for the simulation harness and behavioral tests.

Deterministic: a ``frac`` in [0, ~1.25] drives every scheduled target to that fraction
of its target, so scenarios (perfect / slump / improving) are reproducible.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.scoring.engine import DayInput
from app.scoring.types import HabitSpec, Observation

# Workout scheduled Mon/Tue/Thu/Fri (matches the §22 seed plan; Wed/weekends open).
WORKOUT_WEEKDAYS = {0, 1, 3, 4}


def build_world() -> tuple[dict[str, HabitSpec], list[str], dict[str, float]]:
    """A small multi-domain world resembling the §22 seed (for the harness demo)."""
    habits = {
        "protein": HabitSpec(id="protein", domain="nutrition", importance=5,
                             kind="quantitative", target=160),
        "calories": HabitSpec(id="calories", domain="nutrition", importance=4,
                              kind="quantitative", target=2800),
        "workout": HabitSpec(id="workout", domain="fitness", importance=5, kind="binary"),
        "wake": HabitSpec(id="wake", domain="sleep", importance=3, kind="binary",
                          has_timing=True),
        "brush": HabitSpec(id="brush", domain="routines", importance=2, kind="binary"),
    }
    domains = ["nutrition", "fitness", "sleep", "routines"]
    weights = {d: 1.0 for d in domains}
    return habits, domains, weights


def quant_world(
    importances: tuple[int, ...] = (5, 4),
    targets: tuple[float, ...] = (160, 2800),
    domain: str = "nutrition",
) -> tuple[dict[str, HabitSpec], list[str], dict[str, float]]:
    """A single-domain, all-quantitative world for clean continuous-completion tests."""
    habits = {
        f"h{i}": HabitSpec(id=f"h{i}", domain=domain, importance=imp,
                           kind="quantitative", target=tgt)
        for i, (imp, tgt) in enumerate(zip(importances, targets))
    }
    return habits, [domain], {domain: 1.0}


def _scheduled(habits: dict[str, HabitSpec], d: date):
    for h in habits.values():
        if h.id == "workout" and d.weekday() not in WORKOUT_WEEKDAYS:
            continue
        yield h


def make_day(
    habits: dict[str, HabitSpec],
    d: date,
    frac: float,
    *,
    mode=None,
    only_domains: set[str] | None = None,
) -> DayInput:
    """Build a DayInput where every scheduled target is logged at ``frac`` of target."""
    scheduled: dict[str, Observation] = {}
    for h in _scheduled(habits, d):
        if only_domains is not None and h.domain not in only_domains:
            continue
        if h.kind == "quantitative":
            scheduled[h.id] = Observation(value=frac * (h.target or 0.0))
        else:
            scheduled[h.id] = Observation(
                done=frac >= 0.5,
                timing_in_window=(frac >= 0.8) if h.has_timing else None,
            )
    return DayInput(day=d, scheduled=scheduled, mode=mode)


def days(start: date, n: int):
    return [start + timedelta(days=i) for i in range(n)]

"""Core dataclasses for the scoring engine (spec §7–§9).

Everything the engine needs is expressed here as plain, hashable/inspectable data —
no ORM, no I/O. Domains and habits are referenced by string key/id so the engine is
fully decoupled from the DB (the adapter maps UUIDs <-> these).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Op(str, Enum):
    """Day Mode override primitives (spec §9)."""

    PAUSE = "pause"
    SCALE_TARGET = "scale_target"
    NEUTRALIZE_TIMING = "neutralize_timing"
    EXPECT_MORE = "expect_more"
    SCALE_IMPORTANCE = "scale_importance"


class Scope(str, Enum):
    DOMAIN = "domain"
    HABIT = "habit"
    SYSTEM = "system"


@dataclass(frozen=True)
class Override:
    """One Day Mode adjustment. ``ref`` is a domain key, habit id, or system id
    depending on ``scope``."""

    scope: Scope
    ref: str
    op: Op
    factor: float | None = None
    params: dict | None = None


@dataclass(frozen=True)
class DayMode:
    name: str
    overrides: tuple[Override, ...] = ()


@dataclass(frozen=True)
class ModeEffect:
    """Resolved effect of the active mode on a single scored target (§9)."""

    paused: bool = False
    target_scale: float = 1.0
    timing_neutralized: bool = False
    importance_scale: float = 1.0
    expect_more: bool = False


@dataclass(frozen=True)
class HabitSpec:
    """Static config for a scored target (a habit OR a system — systems score exactly
    like a quantitative habit, §7.4). ``target`` is the pre-mode phase target."""

    id: str
    domain: str                       # domain key
    importance: int                   # 1..5 (§7.2)
    kind: str                         # 'binary' | 'quantitative'
    has_timing: bool = False
    target: float | None = None       # quantitative target; None for binary
    is_system: bool = False           # labeling only (target_kind in outputs)
    system_id: str | None = None      # for system-scope override matching


@dataclass(frozen=True)
class Observation:
    """What actually happened for one scheduled target on one day."""

    value: float | None = None            # quantitative actual (or steps_done for systems)
    done: bool = False                    # binary completion
    timing_in_window: bool | None = None  # None => no timing signal available
    bonus_eligible: bool = False          # unscheduled/overtime flag (§7.5)


@dataclass
class TargetEval:
    """Per-target, per-day scoring record — mirrors the ``day_evaluations`` row (§6.5)."""

    habit_id: str
    domain: str
    target_kind: str                  # 'habit' | 'system'
    was_paused: bool = False
    completion: float | None = None
    completion_baseline: float | None = None
    timing: float | None = None
    timing_baseline: float | None = None
    performance_score: float | None = None
    gain: float = 0.0
    is_new_habit: bool = False
    importance_effective: float | None = None


@dataclass
class DomainDayResult:
    domain: str
    gain_total: float
    decay: float
    active_expectations: int          # scheduled, non-paused targets that day
    lp_before: float
    lp_after: float

    @property
    def lp_change(self) -> float:
        return self.lp_after - self.lp_before


@dataclass
class DayResult:
    day: date
    targets: list[TargetEval] = field(default_factory=list)
    domains: dict[str, DomainDayResult] = field(default_factory=dict)
    xp_earned: int = 0
    xp_total: int = 0

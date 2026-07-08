"""§9 Day Mode override resolution into a per-target ModeEffect."""

import math

from app.scoring.day_modes import resolve_effect
from app.scoring.types import DayMode, HabitSpec, Op, Override, Scope

PROTEIN = HabitSpec(id="protein", domain="nutrition", importance=5, kind="quantitative", target=160)
WORKOUT = HabitSpec(id="workout", domain="fitness", importance=5, kind="binary")
WAKE = HabitSpec(id="wake", domain="sleep", importance=3, kind="binary", has_timing=True)


def test_no_mode_is_identity():
    e = resolve_effect(None, PROTEIN)
    assert e == resolve_effect(DayMode(name="Weekday"), PROTEIN)
    assert e.target_scale == 1.0 and not e.paused


def test_domain_pause_applies_to_member_habit():
    travel = DayMode(name="Travel", overrides=(
        Override(scope=Scope.DOMAIN, ref="fitness", op=Op.PAUSE),
    ))
    assert resolve_effect(travel, WORKOUT).paused is True
    # a non-fitness habit is untouched
    assert resolve_effect(travel, PROTEIN).paused is False


def test_habit_scale_target():
    travel = DayMode(name="Travel", overrides=(
        Override(scope=Scope.HABIT, ref="protein", op=Op.SCALE_TARGET, factor=0.6),
    ))
    assert math.isclose(resolve_effect(travel, PROTEIN).target_scale, 0.6)


def test_scale_targets_multiply():
    mode = DayMode(name="X", overrides=(
        Override(scope=Scope.DOMAIN, ref="nutrition", op=Op.SCALE_TARGET, factor=0.5),
        Override(scope=Scope.HABIT, ref="protein", op=Op.SCALE_TARGET, factor=0.6),
    ))
    assert math.isclose(resolve_effect(mode, PROTEIN).target_scale, 0.3)


def test_neutralize_timing_and_scale_importance():
    mode = DayMode(name="Comp", overrides=(
        Override(scope=Scope.DOMAIN, ref="sleep", op=Op.NEUTRALIZE_TIMING),
        Override(scope=Scope.HABIT, ref="wake", op=Op.SCALE_IMPORTANCE, factor=1.5),
    ))
    e = resolve_effect(mode, WAKE)
    assert e.timing_neutralized is True
    assert math.isclose(e.importance_scale, 1.5)

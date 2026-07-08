"""Resolve a Day Mode's overrides into a single ModeEffect per target (spec §9).

Matching precedence is additive by scope: an override applies to a target if it scopes
that target's domain, the target itself, or (for systems) its system. Multiple
``scale_target`` / ``scale_importance`` overrides multiply (spec §7.2: "product of
scale_target overrides"); any ``pause`` pauses; ``neutralize_timing`` drops timing.
"""

from __future__ import annotations

from app.scoring.types import DayMode, HabitSpec, ModeEffect, Op, Override, Scope


def _applies(ov: Override, spec: HabitSpec) -> bool:
    if ov.scope == Scope.DOMAIN:
        return ov.ref == spec.domain
    if ov.scope == Scope.HABIT:
        return ov.ref == spec.id
    if ov.scope == Scope.SYSTEM:
        return spec.system_id is not None and ov.ref == spec.system_id
    return False


def resolve_effect(mode: DayMode | None, spec: HabitSpec) -> ModeEffect:
    if mode is None:
        return ModeEffect()

    paused = False
    target_scale = 1.0
    timing_neutralized = False
    importance_scale = 1.0
    expect_more = False

    for ov in mode.overrides:
        if not _applies(ov, spec):
            continue
        if ov.op == Op.PAUSE:
            paused = True
        elif ov.op == Op.SCALE_TARGET:
            target_scale *= ov.factor if ov.factor is not None else 1.0
        elif ov.op == Op.NEUTRALIZE_TIMING:
            timing_neutralized = True
        elif ov.op == Op.SCALE_IMPORTANCE:
            importance_scale *= ov.factor if ov.factor is not None else 1.0
        elif ov.op == Op.EXPECT_MORE:
            expect_more = True

    return ModeEffect(
        paused=paused,
        target_scale=target_scale,
        timing_neutralized=timing_neutralized,
        importance_scale=importance_scale,
        expect_more=expect_more,
    )

"""Per-habit daily performance score and LP gain (spec §7.2).

Pure functions: completion from a log, then the three-term performance score, then the
importance-weighted LP gain — with the new-habit grace clamp.
"""

from __future__ import annotations

from app.config import ScoringConfig


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def completion_for(
    kind: str,
    *,
    value: float | None,
    done: bool,
    effective_target: float | None,
    cfg: ScoringConfig,
) -> float:
    """actual / target, clamped to [0, COMPLETION_CAP]; binary => 1 if logged else 0 (§7.2)."""
    if kind == "binary":
        return 1.0 if done else 0.0
    # quantitative
    if effective_target is None or effective_target <= 0:
        # No meaningful target => treat any positive log as full completion.
        return 1.0 if (value or 0.0) > 0 else 0.0
    if value is None:
        return 0.0
    return clamp(value / effective_target, 0.0, cfg.completion_cap)


def performance_score(
    *,
    completion: float,
    baseline: float,
    timing: float | None,
    timing_baseline: float | None,
    timing_active: bool,
    cfg: ScoringConfig,
) -> float:
    """W_ABS*(completion-PASS_LINE) + W_IMP*(completion-baseline) + W_TIMING_eff*(timing-baseline).

    ``timing_active`` is False when the habit has no timing window or the active mode
    neutralizes it, which zeroes the timing term (W_TIMING_eff = 0, §7.2). Weights are
    NOT renormalized in that case, per spec.
    """
    absolute_term = completion - cfg.pass_line
    improvement_term = completion - baseline
    if timing_active and timing is not None and timing_baseline is not None:
        timing_term = timing - timing_baseline
        w_timing = cfg.w_timing
    else:
        timing_term = 0.0
        w_timing = 0.0
    return (
        cfg.w_abs * absolute_term
        + cfg.w_imp * improvement_term
        + w_timing * timing_term
    )


def gain_for(
    *,
    performance: float,
    importance: int,
    importance_scale: float,
    is_new_habit: bool,
    cfg: ScoringConfig,
) -> float:
    """gain = BASE_LP_SWING * (importance/3) * performance, with new-habit grace (§7.2)."""
    importance_mult = (importance * importance_scale) / cfg.importance_divisor
    gain = cfg.base_lp_swing * importance_mult * performance
    if is_new_habit:
        # Grace: early days can only help, never hurt (§7.2).
        gain = max(0.0, gain)
    return gain

"""§7.2 per-habit performance score + gain, incl. new-habit grace."""

import math

from app.config import DEFAULT_SCORING as CFG
from app.scoring.performance import completion_for, gain_for, performance_score


def test_completion_binary():
    assert completion_for("binary", value=None, done=True, effective_target=None, cfg=CFG) == 1.0
    assert completion_for("binary", value=None, done=False, effective_target=None, cfg=CFG) == 0.0


def test_completion_quantitative_clamped_to_cap():
    # 200/80 = 2.5 -> clamped to COMPLETION_CAP (1.25)
    assert completion_for("quantitative", value=200, done=False, effective_target=80, cfg=CFG) == CFG.completion_cap
    assert completion_for("quantitative", value=40, done=False, effective_target=80, cfg=CFG) == 0.5
    assert completion_for("quantitative", value=None, done=False, effective_target=80, cfg=CFG) == 0.0


def test_absolute_term_makes_target_hit_net_positive():
    # completion 1.0, baseline caught up (1.0), no timing -> only absolute term contributes
    perf = performance_score(completion=1.0, baseline=1.0, timing=None,
                             timing_baseline=None, timing_active=False, cfg=CFG)
    # W_ABS * (1.0 - PASS_LINE) = 0.5 * 0.5 = 0.25
    assert math.isclose(perf, 0.25)


def test_missing_entirely_is_net_negative():
    perf = performance_score(completion=0.0, baseline=0.0, timing=None,
                             timing_baseline=None, timing_active=False, cfg=CFG)
    # 0.5*(0-0.5) + 0.35*(0-0) = -0.25
    assert math.isclose(perf, -0.25)


def test_improvement_term_rewards_beating_baseline():
    perf = performance_score(completion=1.0, baseline=0.5, timing=None,
                             timing_baseline=None, timing_active=False, cfg=CFG)
    # 0.5*0.5 + 0.35*0.5 = 0.425
    assert math.isclose(perf, 0.425)


def test_timing_term_included_only_when_active():
    with_timing = performance_score(completion=1.0, baseline=1.0, timing=1.0,
                                    timing_baseline=0.0, timing_active=True, cfg=CFG)
    # adds W_TIMING*(1-0) = 0.15 on top of 0.25
    assert math.isclose(with_timing, 0.40)
    without = performance_score(completion=1.0, baseline=1.0, timing=1.0,
                                timing_baseline=0.0, timing_active=False, cfg=CFG)
    assert math.isclose(without, 0.25)


def test_gain_scales_with_importance():
    perf = 0.25
    g3 = gain_for(performance=perf, importance=3, importance_scale=1.0, is_new_habit=False, cfg=CFG)
    g5 = gain_for(performance=perf, importance=5, importance_scale=1.0, is_new_habit=False, cfg=CFG)
    assert math.isclose(g3, 15 * 1.0 * 0.25)          # 3.75
    assert math.isclose(g5, 15 * (5 / 3) * 0.25)      # 6.25
    assert g5 > g3


def test_new_habit_grace_clamps_negative_gain_to_zero():
    # a bad miss that would normally lose LP costs nothing during grace
    neg = gain_for(performance=-0.25, importance=5, importance_scale=1.0,
                   is_new_habit=True, cfg=CFG)
    assert neg == 0.0
    # but an early win still counts
    pos = gain_for(performance=0.6, importance=5, importance_scale=1.0,
                   is_new_habit=True, cfg=CFG)
    assert pos > 0.0

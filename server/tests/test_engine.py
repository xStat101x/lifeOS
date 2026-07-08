"""Engine orchestration: day-close wires §7.2 -> §7.3 -> §8 correctly."""

import math
from datetime import date

from app.config import DEFAULT_SCORING as CFG
from app.scoring.engine import DayInput, Engine
from app.scoring.types import DayMode, HabitSpec, Observation, Op, Override, Scope


def make_engine():
    habits = {
        "protein": HabitSpec(id="protein", domain="nutrition", importance=5,
                             kind="quantitative", target=160),
        "workout": HabitSpec(id="workout", domain="fitness", importance=5, kind="binary"),
    }
    return Engine(habits=habits, domains=["nutrition", "fitness"], cfg=CFG)


def test_single_day_scores_and_updates_lp():
    eng = make_engine()
    r = eng.process_day(DayInput(day=date(2026, 8, 20),
                                 scheduled={"protein": Observation(value=160)}))
    ev = r.targets[0]
    # new habit (age 0): baseline anchor 0 -> improvement term 1.0; grace clamp keeps >=0
    # perf = 0.5*(1-0.5) + 0.35*(1-0) = 0.6 ; gain = 15*(5/3)*0.6 = 15
    assert math.isclose(ev.completion, 1.0)
    assert math.isclose(ev.gain, 15.0)
    assert math.isclose(eng.lp["nutrition"], 15.0)   # lp_before 0, no decay
    assert r.xp_earned == CFG.xp_per_log
    # fitness had nothing scheduled -> untouched
    assert eng.lp["fitness"] == 0.0


def test_paused_target_is_skipped_entirely():
    eng = make_engine()
    travel = DayMode(name="Travel", overrides=(
        Override(scope=Scope.DOMAIN, ref="fitness", op=Op.PAUSE),
    ))
    r = eng.process_day(DayInput(day=date(2026, 8, 20),
                                 scheduled={"workout": Observation(done=False)},
                                 mode=travel))
    ev = next(t for t in r.targets if t.habit_id == "workout")
    assert ev.was_paused is True
    assert ev.gain == 0.0
    # paused domain: no decay, LP unchanged
    assert eng.lp["fitness"] == 0.0
    assert r.domains["fitness"].decay == 0.0


def test_scale_target_lets_reduced_bar_count_as_met():
    eng = make_engine()
    # burn grace so absolute/improvement behave normally, all at reduced target
    travel = DayMode(name="Travel", overrides=(
        Override(scope=Scope.HABIT, ref="protein", op=Op.SCALE_TARGET, factor=0.6),
    ))
    # hitting 96 against a 0.6*160=96 target => completion 1.0 (met expectations)
    r = eng.process_day(DayInput(day=date(2026, 8, 20),
                                 scheduled={"protein": Observation(value=96)},
                                 mode=travel))
    assert math.isclose(r.targets[0].completion, 1.0)


def test_overall_lp_is_weighted_average():
    eng = make_engine()
    eng.lp["nutrition"] = 400.0
    eng.lp["fitness"] = 200.0
    assert math.isclose(eng.overall_lp(), 300.0)
    assert math.isclose(eng.overall_lp({"nutrition": 3, "fitness": 1}), (400*3 + 200*1) / 4)


def test_season_reset_compresses_all_domains():
    eng = make_engine()
    eng.lp["nutrition"] = 2400.0
    eng.lp["fitness"] = 2000.0
    peaks = eng.apply_season_reset()
    assert peaks["nutrition"] == 2400.0
    assert eng.lp["nutrition"] < 2400.0
    mid = CFG.ladder_midpoint_lp
    assert math.isclose(eng.lp["nutrition"] - mid, (2400.0 - mid) * CFG.reset_compression)

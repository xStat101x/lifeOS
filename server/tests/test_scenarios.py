"""Behavioral proofs on synthetic day-by-day logs (spec §23 step 4).

Each test demonstrates one headline scoring behavior end-to-end through the engine:
1. consistent performance settles at a STABLE rank (no saturation)
2. genuine improvement climbs
3. a slump slides, then self-corrects
4. a fully-paused domain-day neither gains nor decays
5. a retroactive mulligan turns a loss to neutral, never to a win
6. a season reset reclaims peak in ~30 perfect days
"""

import math
from datetime import date

from app.config import DEFAULT_SCORING as CFG
from app.scoring.engine import DayInput, Engine
from app.scoring.equilibrium import equilibrium_lp
from app.scoring.forgiveness import neutralize_domain_day
from app.scoring.types import DayMode, Observation, Op, Override, Scope
from sim.calibration import CALIBRATION_SCORING
from sim.harness import simulate
from sim.scenarios import days, make_day, quant_world

START = date(2026, 8, 20)


def _run(cfg, fracs, mode_for=None):
    """Run a single quantitative domain at the given per-day fractions; return engine+snaps."""
    habits, domains, weights = quant_world()
    eng = Engine(habits=habits, domains=domains, cfg=cfg)
    seq = days(START, len(fracs))
    inputs = [
        make_day(habits, d, f, mode=(mode_for(i) if mode_for else None))
        for i, (d, f) in enumerate(zip(seq, fracs))
    ]
    return eng, simulate(eng, inputs, weights)


# 1 ---------------------------------------------------------------------------
def test_consistent_performance_settles_stable_no_saturation():
    eng, snaps = _run(CFG, [1.0] * 600)
    # steady per-day gain for the two habits (imp5+imp4) at completion 1.0, baseline 1.0
    steady_gain = CFG.base_lp_swing * ((5 + 4) / CFG.importance_divisor) * (
        CFG.w_abs * (1.0 - CFG.pass_line)
    )
    eq = equilibrium_lp(steady_gain, CFG)
    final = eng.lp["nutrition"]
    assert math.isclose(final, eq, rel_tol=1e-3)             # settles AT equilibrium
    assert abs(snaps[-1].domain_lp["nutrition"] - snaps[-2].domain_lp["nutrition"]) < 0.05
    assert eng.lp["nutrition"] < CFG.apex_master_lp          # no runaway to a ceiling


# 2 ---------------------------------------------------------------------------
def test_genuine_improvement_climbs():
    # 250 days hitting target exactly, then 250 days genuinely overachieving (1.25x)
    eng, snaps = _run(CFG, [1.0] * 250 + [1.25] * 250)
    plateau = snaps[249].domain_lp["nutrition"]
    improved = snaps[-1].domain_lp["nutrition"]
    assert improved > plateau + 100        # a higher equilibrium from beating your target


# 3 ---------------------------------------------------------------------------
def test_slump_slides_then_self_corrects():
    eng, snaps = _run(CFG, [1.0] * 150 + [0.1] * 40 + [1.0] * 200)
    before = snaps[149].domain_lp["nutrition"]
    trough = snaps[189].domain_lp["nutrition"]
    recovered = snaps[-1].domain_lp["nutrition"]
    assert trough < before - 50            # the slump slides you down
    assert recovered > trough + 50         # then you self-correct back up
    assert math.isclose(recovered, before, rel_tol=0.1)   # back near the old equilibrium


# 4 ---------------------------------------------------------------------------
def test_fully_paused_domain_day_neither_gains_nor_decays():
    habits, domains, weights = quant_world()
    eng = Engine(habits=habits, domains=domains, cfg=CFG)
    eng.lp["nutrition"] = 500.0
    pause_nutrition = DayMode(name="Away", overrides=(
        Override(scope=Scope.DOMAIN, ref="nutrition", op=Op.PAUSE),
    ))
    r = eng.process_day(make_day(habits, START, 1.0, mode=pause_nutrition))
    assert all(t.was_paused for t in r.targets)
    assert r.domains["nutrition"].active_expectations == 0
    assert r.domains["nutrition"].decay == 0.0
    assert eng.lp["nutrition"] == 500.0    # unchanged: no gain, no decay


# 5 ---------------------------------------------------------------------------
def test_retroactive_mulligan_loss_to_neutral_never_win():
    habits, domains, weights = quant_world()
    eng = Engine(habits=habits, domains=domains, cfg=CFG)
    eng.lp["nutrition"] = 300.0
    lp_before = eng.lp["nutrition"]
    # a detonated day: logged nothing -> big negative day
    r = eng.process_day(make_day(habits, START, 0.0))
    day_change = r.domains["nutrition"].lp_change
    assert day_change < 0                                   # it really was a loss

    # apply a mulligan: erase the loss -> the day's contribution becomes neutral (0)
    adjusted = neutralize_domain_day(day_change)
    assert adjusted == 0.0
    restored_lp = lp_before + adjusted
    assert math.isclose(restored_lp, lp_before)             # loss erased
    assert restored_lp <= lp_before                         # NEVER converted into a win


# 6 ---------------------------------------------------------------------------
def test_season_reset_reclaims_peak_in_about_30_perfect_days():
    cfg = CALIBRATION_SCORING            # spec defaults don't meet this target (DECISIONS.md)
    # climb to peak with sustained perfect play
    eng, _ = _run(cfg, [1.0] * 300)
    peak = eng.lp["nutrition"]
    assert peak > cfg.ladder_midpoint_lp          # disciplined equilibrium sits above midpoint

    eng.apply_season_reset()
    reset_lp = eng.lp["nutrition"]
    assert cfg.lp_floor < reset_lp < peak         # demoted, not wiped

    # 30 more perfect days
    seq = days(START, 30)
    habits = {"h0": eng.habits["h0"], "h1": eng.habits["h1"]}
    for d in seq:
        eng.process_day(make_day(habits, d, 1.0))
    after_30 = eng.lp["nutrition"]

    assert after_30 >= 0.95 * peak                # reclaimed the bulk of peak in ~a month
    assert after_30 <= peak + 1e-6               # but did NOT surpass peak w/o better play

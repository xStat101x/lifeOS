"""Per-domain mass normalization (§7.3, DECISIONS.md).

Full compliance in any domain must equilibrate to the same target rank regardless of how
many habits it holds. Importance still governs within-domain weighting.
"""

import math
from datetime import date

from dataclasses import replace

from app.config import ACTIVE_SCORING, DEFAULT_SCORING
from app.scoring.engine import Engine
from app.scoring.equilibrium import equilibrium_lp, update_domain_lp
from app.scoring.types import HabitSpec, Observation
from sim.scenarios import days, make_day

START = date(2026, 8, 20)


def _run_to_equilibrium(cfg, habits, warmup=3000):
    domains = sorted({h.domain for h in habits.values()})
    eng = Engine(habits=habits, domains=domains, cfg=cfg)
    for d in days(START, warmup):
        eng.process_day(make_day(habits, d, 1.0))
    return eng


def test_equilibrium_is_mass_independent_when_normalized():
    # one domain with a single imp-3 habit vs one with three imp-5 habits
    light = {"a": HabitSpec(id="a", domain="light", importance=3, kind="quantitative", target=100)}
    heavy = {
        f"h{i}": HabitSpec(id=f"h{i}", domain="heavy", importance=5,
                           kind="quantitative", target=100)
        for i in range(3)
    }
    eng_light = _run_to_equilibrium(ACTIVE_SCORING, light)
    eng_heavy = _run_to_equilibrium(ACTIVE_SCORING, heavy)
    # both settle at the same target LP despite very different habit-mass
    assert math.isclose(eng_light.lp["light"], eng_heavy.lp["heavy"], rel_tol=0.02)
    # and at the closed-form target base*perf/decay_rate
    perf = ACTIVE_SCORING.w_abs * (1.0 - ACTIVE_SCORING.pass_line)
    target = ACTIVE_SCORING.base_lp_swing * perf / ACTIVE_SCORING.decay_rate
    assert math.isclose(eng_light.lp["light"], target, rel_tol=0.02)


def test_without_normalization_equilibrium_scales_with_mass():
    # DEFAULT_SCORING keeps normalization OFF -> heavier domain settles higher (old behavior)
    light = {"a": HabitSpec(id="a", domain="light", importance=3, kind="quantitative", target=100)}
    heavy = {
        f"h{i}": HabitSpec(id=f"h{i}", domain="heavy", importance=5,
                           kind="quantitative", target=100)
        for i in range(3)
    }
    eng_light = _run_to_equilibrium(DEFAULT_SCORING, light)
    eng_heavy = _run_to_equilibrium(DEFAULT_SCORING, heavy)
    assert eng_heavy.lp["heavy"] > eng_light.lp["light"] * 3


def test_mass_scaled_decay_only_active_when_flag_on():
    on = replace(DEFAULT_SCORING, normalize_domain_mass=True)
    off = replace(DEFAULT_SCORING, normalize_domain_mass=False)
    kw = dict(lp_before=1000.0, gain_total=0.0, active_expectations=2, mass=3.0)
    assert math.isclose(update_domain_lp(cfg=on, **kw).decay,
                        off.decay_rate * 3.0 * 1000.0)
    assert math.isclose(update_domain_lp(cfg=off, **kw).decay,
                        off.decay_rate * 1000.0)


def test_equilibrium_helper_respects_mass_flag():
    on = replace(DEFAULT_SCORING, normalize_domain_mass=True)
    # with normalization, doubling mass halves the equilibrium for the same gain
    assert math.isclose(equilibrium_lp(10.0, on, mass=2.0),
                        equilibrium_lp(10.0, on, mass=1.0) / 2)
    # without, mass is ignored
    assert math.isclose(equilibrium_lp(10.0, DEFAULT_SCORING, mass=2.0),
                        equilibrium_lp(10.0, DEFAULT_SCORING, mass=1.0))

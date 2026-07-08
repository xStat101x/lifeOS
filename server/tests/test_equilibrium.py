"""§7.3 domain LP update: gain minus rank-proportional decay."""

import math

from app.config import DEFAULT_SCORING as CFG
from app.scoring.equilibrium import equilibrium_lp, update_domain_lp


def test_gain_minus_decay():
    upd = update_domain_lp(lp_before=100.0, gain_total=5.0, active_expectations=2, cfg=CFG)
    assert math.isclose(upd.decay, CFG.decay_rate * 100.0)   # 2.0
    assert math.isclose(upd.lp_after, 100.0 + 5.0 - 2.0)     # 103.0


def test_decay_grows_with_rank():
    low = update_domain_lp(lp_before=100.0, gain_total=0.0, active_expectations=1, cfg=CFG)
    high = update_domain_lp(lp_before=1000.0, gain_total=0.0, active_expectations=1, cfg=CFG)
    assert high.decay > low.decay


def test_rest_day_suspends_decay():
    # all expectations paused / nothing scheduled -> no gain, no decay (§7.3, §7.5)
    upd = update_domain_lp(lp_before=500.0, gain_total=0.0, active_expectations=0, cfg=CFG)
    assert upd.decay == 0.0
    assert upd.lp_after == 500.0


def test_lp_never_below_floor():
    upd = update_domain_lp(lp_before=1.0, gain_total=-100.0, active_expectations=1, cfg=CFG)
    assert upd.lp_after == CFG.lp_floor


def test_equilibrium_is_gain_over_decay_rate():
    # sustained gain of 5/active-day settles at 5 / 0.02 = 250
    assert math.isclose(equilibrium_lp(5.0, CFG), 250.0)


def test_sustained_gain_converges_to_equilibrium_no_saturation():
    # A fixed per-day gain must settle at a finite, stable LP — not run away to a ceiling.
    lp = 0.0
    gain = 6.0
    for _ in range(2000):
        lp = update_domain_lp(lp_before=lp, gain_total=gain,
                              active_expectations=1, cfg=CFG).lp_after
    assert math.isclose(lp, equilibrium_lp(gain, CFG), rel_tol=1e-6)

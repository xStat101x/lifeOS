"""§7.8 season soft reset (compression toward the ladder midpoint)."""

import math

from app.config import DEFAULT_SCORING as CFG
from app.scoring.seasons import bank_peak, soft_reset_lp


def test_reset_compresses_toward_midpoint_not_zero():
    old = 2400.0  # Diamond-ish
    new = soft_reset_lp(old, CFG)
    mid = CFG.ladder_midpoint_lp
    # distance to midpoint shrinks by exactly reset_compression
    assert math.isclose(new - mid, (old - mid) * CFG.reset_compression)
    assert new > mid                 # still well above zero
    assert new < old                 # but demoted


def test_reset_never_below_floor():
    assert soft_reset_lp(0.0, CFG) >= CFG.lp_floor


def test_bank_peak_returns_rank():
    r = bank_peak(2650.0, CFG)  # Diamond II region (2600-2699)
    assert r.tier == "Diamond"
    assert r.division == 2

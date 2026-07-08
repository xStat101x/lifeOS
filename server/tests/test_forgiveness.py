"""§8.3 mulligan: loss -> neutral, never a win; escalating cost + cap."""

import pytest

from app.config import DEFAULT_SCORING as CFG
from app.scoring.forgiveness import (
    clamp_never_win,
    mulligan_cost,
    neutralize_domain_day,
)


def test_neutralize_turns_loss_into_zero():
    assert neutralize_domain_day(-8.0) == 0.0


def test_neutralize_never_creates_a_win():
    # even a strongly-negative day only reaches neutral, never positive
    assert neutralize_domain_day(-100.0) == 0.0


def test_retroactive_mode_clamped_to_neutral():
    # a generous retroactive mode could compute a positive day; it is clamped to <= 0
    assert clamp_never_win(5.0) == 0.0
    # but it can still reduce a loss toward neutral
    assert clamp_never_win(-2.0) == -2.0


def test_cost_escalates():
    assert mulligan_cost(0, CFG) == 200
    assert mulligan_cost(1, CFG) == 400
    assert mulligan_cost(2, CFG) == 800


def test_cap_enforced():
    with pytest.raises(ValueError):
        mulligan_cost(CFG.mulligan_cap_per_month, CFG)

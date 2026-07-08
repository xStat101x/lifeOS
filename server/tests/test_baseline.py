"""§7.2 rolling baseline + habit age / grace window."""

import math

from app.config import DEFAULT_SCORING as CFG
from app.scoring.baseline import BaselineTracker


def test_new_habit_uses_low_anchor_during_grace():
    bt = BaselineTracker(CFG)
    # record a few strong days but still inside grace window
    for _ in range(3):
        assert bt.is_new_habit("h") is True
        assert bt.completion_baseline("h") == CFG.new_habit_baseline_anchor
        bt.record("h", 1.0, None)
    assert bt.age("h") == 3


def test_grace_ends_after_window_and_baseline_becomes_mean():
    bt = BaselineTracker(CFG)
    for _ in range(CFG.new_habit_grace_days):
        bt.record("h", 1.0, None)
    assert bt.age("h") == CFG.new_habit_grace_days
    assert bt.is_new_habit("h") is False
    assert math.isclose(bt.completion_baseline("h"), 1.0)


def test_baseline_is_mean_of_window():
    bt = BaselineTracker(CFG)
    for _ in range(CFG.new_habit_grace_days):
        bt.record("h", 0.0, None)  # exit grace with zeros
    bt.record("h", 1.0, None)
    bt.record("h", 1.0, None)
    # window mean over grace_days zeros + two ones
    hist_len = CFG.new_habit_grace_days + 2
    assert math.isclose(bt.completion_baseline("h"), 2.0 / hist_len)


def test_window_is_bounded():
    bt = BaselineTracker(CFG)
    for _ in range(CFG.baseline_window + 20):
        bt.record("h", 1.0, None)
    # only the last BASELINE_WINDOW entries are retained; mean of all-ones is 1.0
    assert math.isclose(bt.completion_baseline("h"), 1.0)
    assert bt.age("h") == CFG.baseline_window + 20  # age keeps counting


def test_timing_baseline_tracks_only_timing_days():
    bt = BaselineTracker(CFG)
    bt.record("h", 1.0, 1.0)
    bt.record("h", 1.0, 0.0)
    bt.record("h", 1.0, None)  # no timing signal that day
    assert math.isclose(bt.timing_baseline("h"), 0.5)

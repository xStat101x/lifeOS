"""§8 XP earning, level curve, reward tokens."""

from app.config import DEFAULT_SCORING as CFG
from app.scoring.xp import day_xp, level_for_total_xp
from app.scoring.types import Observation


def test_base_xp_per_qualifying_log():
    scheduled = {"a": Observation(done=True), "b": Observation(value=50)}
    completions = {"a": 1.0, "b": 0.5}
    assert day_xp(scheduled, completions, CFG) == 2 * CFG.xp_per_log


def test_unlogged_target_earns_no_xp():
    scheduled = {"a": Observation(done=False, value=None)}
    assert day_xp(scheduled, {"a": 0.0}, CFG) == 0


def test_overtime_earns_bonus():
    scheduled = {"a": Observation(value=200)}
    completions = {"a": 1.25}  # beyond target
    assert day_xp(scheduled, completions, CFG) == CFG.xp_per_log + CFG.xp_bonus_overtime


def test_level_curve_increasing():
    # level 1->2 costs 100, 2->3 costs 200
    assert level_for_total_xp(0, CFG).level == 1
    assert level_for_total_xp(100, CFG).level == 2
    assert level_for_total_xp(300, CFG).level == 3          # 100 + 200
    assert level_for_total_xp(299, CFG).level == 2


def test_reward_token_every_ten_levels():
    # XP to reach level 10 = sum_{L=1..9} 100L = 4500
    st = level_for_total_xp(4500, CFG)
    assert st.level == 10
    assert st.reward_tokens == 1
    assert level_for_total_xp(4499, CFG).reward_tokens == 0

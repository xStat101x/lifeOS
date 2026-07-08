"""§7.7 LP <-> tier/division mapping."""

from app.config import DEFAULT_SCORING as CFG
from app.scoring.ladder import lp_to_rank


def test_bottom_is_iron_iv():
    r = lp_to_rank(0.0, CFG)
    assert (r.tier, r.division) == ("Iron", 4)


def test_iron_i_just_below_bronze():
    r = lp_to_rank(350.0, CFG)
    assert (r.tier, r.division) == ("Iron", 1)
    assert r.lp_in_division == 50.0


def test_midpoint_is_gold_ii():
    r = lp_to_rank(CFG.ladder_midpoint_lp, CFG)  # 1400
    assert (r.tier, r.division) == ("Gold", 2)


def test_diamond_and_apex_boundaries():
    assert lp_to_rank(2700.0, CFG).tier == "Diamond"
    assert lp_to_rank(2800.0, CFG).tier == "Master"
    assert lp_to_rank(2800.0, CFG).division is None
    assert lp_to_rank(3300.0, CFG).tier == "Grandmaster"
    assert lp_to_rank(3700.0, CFG).tier == "Challenger"


def test_labels():
    assert lp_to_rank(1400.0, CFG).label() == "Gold II"
    assert lp_to_rank(2850.0, CFG).label().startswith("Master")

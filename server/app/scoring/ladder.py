"""LP <-> tier/division mapping (spec §7.7).

Iron..Diamond: 7 tiers x 4 divisions x LP_PER_DIVISION each. Master/Grandmaster/
Challenger: apex, single-player => fixed LP thresholds, no divisions.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import ScoringConfig

TIERS = ["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond"]
_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}


@dataclass(frozen=True)
class Rank:
    tier: str
    division: int | None      # 1..4 (I highest, IV lowest); None for apex
    lp_total: float
    lp_in_division: float     # LP within the current division / above apex floor

    def label(self) -> str:
        if self.division is None:
            return f"{self.tier} ({int(self.lp_in_division)} LP)"
        return f"{self.tier} {_ROMAN[self.division]}"


def lp_to_rank(lp: float, cfg: ScoringConfig) -> Rank:
    lp = max(cfg.lp_floor, lp)
    per_div = cfg.lp_per_division
    per_tier = per_div * 4
    divisioned_ceiling = per_tier * len(TIERS)  # start of apex

    if lp < divisioned_ceiling:
        tier_idx = int(lp // per_tier)
        within_tier = lp - tier_idx * per_tier
        div_from_bottom = int(within_tier // per_div)      # 0=IV .. 3=I
        division = 4 - div_from_bottom
        return Rank(
            tier=TIERS[tier_idx],
            division=division,
            lp_total=lp,
            lp_in_division=within_tier - div_from_bottom * per_div,
        )

    # Apex
    if lp < cfg.apex_grandmaster_lp:
        tier = "Master"
    elif lp < cfg.apex_challenger_lp:
        tier = "Grandmaster"
    else:
        tier = "Challenger"
    return Rank(tier=tier, division=None, lp_total=lp,
                lp_in_division=lp - cfg.apex_master_lp)

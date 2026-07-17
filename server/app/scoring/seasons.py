"""Season soft reset (spec §7.8).

At rollover, ranks compress toward the ladder midpoint — NOT to zero — so a Diamond
drops to roughly Gold and re-climbs. Previous peak is banked (returned for the caller
to persist in ``rank_peaks``). XP/level never reset (handled elsewhere; not touched here).
"""

from __future__ import annotations

from app.config import ScoringConfig
from app.scoring.ladder import Rank, lp_to_rank


def soft_reset_lp(old_lp: float, cfg: ScoringConfig) -> float:
    """Compress toward midpoint, but never promote without performance.

    The literal compression formula raises LP below the midpoint. Rank may only rise
    from doing the thing, so a reset can demote an above-midpoint player or hold a
    below-midpoint player; it can never increase LP.
    """
    mid = cfg.ladder_midpoint_lp
    compressed = mid + (old_lp - mid) * cfg.reset_compression
    new_lp = min(old_lp, compressed)
    return max(cfg.lp_floor, new_lp)


def bank_peak(peak_lp: float, cfg: ScoringConfig) -> Rank:
    """Rank record to store for a season's peak LP ('Season 1 peak: Diamond II')."""
    return lp_to_rank(peak_lp, cfg)

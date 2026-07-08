"""Retroactive mulligan (spec §8.3).

Hard invariant (§0 rule 3, §8.3): a mulligan converts a past day's *loss* to *neutral*,
or applies a Day Mode retroactively (reduced expectation) — but NEVER produces a win.
So the mulligan-adjusted domain LP change for the day is clamped to at most 0.

Two paths:
- ``neutralize_domain_day``: erase the day's loss -> LP change becomes 0.
- ``retroactive_mode_lp_change``: re-score the day under a mode, then clamp to <= 0,
  so even a generous mode can only reduce the loss, never manufacture a gain.

Cost/cap accounting (escalating cost, MULLIGAN_CAP/month) is enforced by the caller
using ``mulligan_cost`` before applying either path.
"""

from __future__ import annotations

from app.config import ScoringConfig


def neutralize_domain_day(original_lp_change: float) -> float:
    """Convert a losing day to neutral. A loss (<0) becomes 0; never turns into a win."""
    return max(0.0, original_lp_change) if original_lp_change < 0 else original_lp_change


def clamp_never_win(recomputed_lp_change: float) -> float:
    """Clamp a retroactively re-scored day so it can never exceed neutral (§8.3)."""
    return min(0.0, recomputed_lp_change)


def mulligan_cost(prior_mulligans_this_month: int, cfg: ScoringConfig) -> int:
    """Escalating XP cost for the n-th mulligan this month; raises past the cap (§8.3)."""
    if prior_mulligans_this_month >= cfg.mulligan_cap_per_month:
        raise ValueError(
            f"Mulligan cap reached ({cfg.mulligan_cap_per_month}/month)."
        )
    ladder = cfg.mulligan_cost_ladder
    idx = min(prior_mulligans_this_month, len(ladder) - 1)
    return ladder[idx]

"""Calibration analysis for the tunable scoring constants (spec §7.8, §25).

Season 1 is explicitly a calibration run. This module measures, for a given config and a
representative disciplined-domain daily gain, (a) the equilibrium LP / rank a sustained
performer settles at, and (b) how many perfect days it takes to reclaim peak after a
season soft-reset — the spec's headline calibration target ("a perfect ~30 days reclaims
your previous peak").

Finding (recorded in DECISIONS.md): the spec's *default* constants
(BASE_LP_SWING=15, DECAY_RATE=0.02) do NOT meet that target — equilibria land far below
the ladder midpoint and reclaim takes ~150 days. ``CALIBRATION_SCORING`` below is a
self-consistent candidate that does; the owner picks the final levers in Season 1.
"""

from __future__ import annotations

from app.config import ACTIVE_SCORING, DEFAULT_SCORING, ScoringConfig
from app.scoring.equilibrium import equilibrium_lp, update_domain_lp
from app.scoring.ladder import lp_to_rank
from app.scoring.seasons import soft_reset_lp

# The adopted Season-1 active config (lever A: bigger LP swing + faster decay) so a
# disciplined 2-habit domain equilibrates above the 1400 midpoint (the reset demotes)
# and a perfect ~30 days reclaims peak. This IS ``config.ACTIVE_SCORING``; kept under the
# historical name so the season-reclaim test reads clearly. See DECISIONS.md for the
# derivation and the alternative lever (shrinking the ladder scale instead).
CALIBRATION_SCORING: ScoringConfig = ACTIVE_SCORING


def reclaim_report(steady_gain: float, cfg: ScoringConfig,
                   *, threshold: float = 0.97, warmup: int = 800) -> dict:
    """Drive a single domain at a fixed per-day gain to equilibrium, soft-reset, then
    count perfect days to climb back to ``threshold`` of peak."""
    lp = 0.0
    for _ in range(warmup):
        lp = update_domain_lp(lp_before=lp, gain_total=steady_gain,
                              active_expectations=1, cfg=cfg).lp_after
    peak = lp
    lp = soft_reset_lp(peak, cfg)
    reset_lp = lp
    day = 0
    while lp < threshold * peak and day < 5000:
        lp = update_domain_lp(lp_before=lp, gain_total=steady_gain,
                              active_expectations=1, cfg=cfg).lp_after
        day += 1
    return {
        "steady_gain": steady_gain,
        "equilibrium_lp": equilibrium_lp(steady_gain, cfg),
        "peak_lp": peak,
        "peak_rank": lp_to_rank(peak, cfg).label(),
        "reset_lp": reset_lp,
        "reset_rank": lp_to_rank(reset_lp, cfg).label(),
        "days_to_reclaim": day,
        "threshold": threshold,
    }


def _fmt(r: dict) -> str:
    return (
        f"  gain/day={r['steady_gain']:.1f}  eq_LP={r['equilibrium_lp']:.0f} "
        f"({r['peak_rank']})  reset->{r['reset_lp']:.0f} ({r['reset_rank']})  "
        f"reclaim {int(r['threshold']*100)}% in {r['days_to_reclaim']}d"
    )


if __name__ == "__main__":
    # Representative disciplined nutrition-ish domain: protein(imp5)+calories(imp4),
    # sustained perfect -> steady per-day gain under each config.
    for name, cfg in [("DEFAULT (literal spec)", DEFAULT_SCORING),
                      ("ACTIVE (adopted, lever A)", ACTIVE_SCORING)]:
        # steady perfect gain_total for 2 habits (imp5, imp4) at completion 1.0, baseline 1.0
        perf = cfg.w_abs * (1.0 - cfg.pass_line)  # 0.25
        gain = cfg.base_lp_swing * ((5 + 4) / cfg.importance_divisor) * perf
        print(f"{name}:")
        print(_fmt(reclaim_report(gain, cfg)))

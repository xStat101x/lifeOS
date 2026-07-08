"""Calibration analysis for the tunable scoring constants (spec §7.8, §25).

Season 1 is explicitly a calibration run. This module measures, for a given config:
(a) the equilibrium LP / rank a sustained performer settles at and the perfect-days to
reclaim peak after a season soft-reset (the spec's headline target), and
(b) the per-domain full-compliance equilibria across a realistic multi-domain world —
used to verify that mass normalization makes domains rank comparably.

Findings recorded in DECISIONS.md:
- Literal-spec constants (BASE_LP_SWING=15, DECAY_RATE=0.02) leave equilibria far below
  the ladder midpoint and reclaim takes ~150 days -> reset inverts.
- Even after lever A, per-domain equilibria scaled with each domain's habit-mass, so
  single-habit domains (sleep/routines) ranked far below nutrition and dragged the
  overall average down. Mass normalization fixes that.
"""

from __future__ import annotations

from datetime import date

from app.config import ACTIVE_SCORING, DEFAULT_SCORING, ScoringConfig
from app.scoring.engine import Engine
from app.scoring.equilibrium import equilibrium_lp, update_domain_lp
from app.scoring.ladder import lp_to_rank
from app.scoring.seasons import soft_reset_lp
from sim.scenarios import build_world, days, make_day

#: The adopted Season-1 active config (lever A + mass normalization). This IS
#: ``config.ACTIVE_SCORING``; aliased so the season-reclaim test reads clearly.
CALIBRATION_SCORING: ScoringConfig = ACTIVE_SCORING


def reclaim_report(steady_gain: float, cfg: ScoringConfig, *, mass: float = 1.0,
                   threshold: float = 0.97, warmup: int = 2000) -> dict:
    """Drive a single domain at a fixed per-day gain to equilibrium, soft-reset, then
    count perfect days to climb back to ``threshold`` of peak."""
    lp = 0.0
    for _ in range(warmup):
        lp = update_domain_lp(lp_before=lp, gain_total=steady_gain,
                              active_expectations=1, cfg=cfg, mass=mass).lp_after
    peak = lp
    lp = soft_reset_lp(peak, cfg)
    reset_lp = lp
    day = 0
    while lp < threshold * peak and day < 5000:
        lp = update_domain_lp(lp_before=lp, gain_total=steady_gain,
                              active_expectations=1, cfg=cfg, mass=mass).lp_after
        day += 1
    return {
        "steady_gain": steady_gain,
        "equilibrium_lp": equilibrium_lp(steady_gain, cfg, mass),
        "peak_lp": peak, "peak_rank": lp_to_rank(peak, cfg).label(),
        "reset_lp": reset_lp, "reset_rank": lp_to_rank(reset_lp, cfg).label(),
        "days_to_reclaim": day, "threshold": threshold,
    }


def domain_equilibria(cfg: ScoringConfig, *, warmup: int = 3000) -> tuple[dict, float]:
    """Full-compliance equilibrium LP + rank per domain in the seed-like world (§22)."""
    habits, domains, weights = build_world()
    eng = Engine(habits=habits, domains=domains, cfg=cfg)
    start = date(2026, 8, 20)
    for d in days(start, warmup):
        eng.process_day(make_day(habits, d, 1.0))
    per_domain = {dm: (eng.lp[dm], lp_to_rank(eng.lp[dm], cfg).label()) for dm in domains}
    return per_domain, eng.overall_lp(weights)


def _fmt_reclaim(r: dict) -> str:
    return (
        f"  gain/day={r['steady_gain']:.1f}  eq_LP={r['equilibrium_lp']:.0f} "
        f"({r['peak_rank']})  reset->{r['reset_lp']:.0f} ({r['reset_rank']})  "
        f"reclaim {int(r['threshold']*100)}% in {r['days_to_reclaim']}d"
    )


def _print_domains(title: str, cfg: ScoringConfig) -> None:
    per_domain, overall = domain_equilibria(cfg)
    print(f"{title}:")
    for dm, (lp, rank) in per_domain.items():
        print(f"    {dm:<9} eq_LP={lp:>6.0f}   {rank}")
    print(f"    {'OVERALL':<9} eq_LP={overall:>6.0f}   {lp_to_rank(overall, cfg).label()}")


if __name__ == "__main__":
    # Pre-normalization ACTIVE (lever A only) for the before/after comparison.
    from dataclasses import replace
    BEFORE = replace(DEFAULT_SCORING, base_lp_swing=200.0, decay_rate=0.075)

    print("=== Reclaim (nutrition-scale domain, mass=3) ===")
    for name, cfg in [("DEFAULT (literal spec)", DEFAULT_SCORING),
                      ("ACTIVE (adopted)", ACTIVE_SCORING)]:
        perf = cfg.w_abs * (1.0 - cfg.pass_line)
        mass = (5 + 4) / cfg.importance_divisor
        gain = cfg.base_lp_swing * mass * perf
        print(f"{name}:")
        print(_fmt_reclaim(reclaim_report(gain, cfg, mass=mass)))

    print("\n=== Per-domain full-compliance equilibria ===")
    _print_domains("BEFORE (lever A, no normalization)", BEFORE)
    _print_domains("AFTER  (ACTIVE: lever A + mass normalization)", ACTIVE_SCORING)

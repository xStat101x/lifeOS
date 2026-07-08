"""Domain-level LP update: gain minus rank-proportional decay (spec §7.3).

This is where the equilibrium lives (§7.1). Rank settles where per-day gain equals
decay, and decay grows with current LP — so sustained excellence holds a stable high
rank instead of saturating.

Decay is suspended for a domain on any day with no *active* expectation (all scheduled
targets paused, or nothing scheduled) so legitimate rest is never punished (§7.3, §7.5).

Optional mass normalization (``cfg.normalize_domain_mass``): decay is scaled by the
domain's active habit-mass (Σ importance/divisor). At full compliance a domain's daily
gain also scales with that mass, so the two cancel and the equilibrium LP becomes
mass-independent (base_lp_swing * perf / decay_rate) — single-habit domains rank the same
as many-habit ones. Note this makes the effective reclaim rate ``decay_rate * mass``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import ScoringConfig


@dataclass(frozen=True)
class LPUpdate:
    lp_after: float
    decay: float
    lp_before: float
    gain_total: float


def update_domain_lp(
    *,
    lp_before: float,
    gain_total: float,
    active_expectations: int,
    cfg: ScoringConfig,
    mass: float = 1.0,
) -> LPUpdate:
    if active_expectations <= 0:
        # Rest day for this domain: neither gain nor decay (§7.3).
        return LPUpdate(lp_after=lp_before, decay=0.0, lp_before=lp_before,
                        gain_total=0.0)
    mass_factor = mass if cfg.normalize_domain_mass else 1.0
    decay = cfg.decay_rate * mass_factor * max(0.0, lp_before - cfg.lp_floor)
    lp_after = max(cfg.lp_floor, lp_before + gain_total - decay)
    return LPUpdate(lp_after=lp_after, decay=decay, lp_before=lp_before,
                    gain_total=gain_total)


def equilibrium_lp(
    gain_total_per_active_day: float, cfg: ScoringConfig, mass: float = 1.0
) -> float:
    """Closed-form equilibrium: where gain_total == decay.

    decay == DECAY_RATE * mass_factor * (lp - FLOOR). Handy for calibration/tests;
    assumes a steady per-active-day gain. ``mass`` is ignored unless normalization is on.
    """
    if cfg.decay_rate <= 0:
        return float("inf")
    mass_factor = mass if cfg.normalize_domain_mass else 1.0
    return cfg.lp_floor + gain_total_per_active_day / (cfg.decay_rate * mass_factor)

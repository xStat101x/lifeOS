"""XP, levels, and reward tokens (spec §8).

XP is the *participation* currency: earned for showing up at all, so even a net-negative
rank day yields progress, and XP is NEVER reduced by a bad day (§8.1). Separate from
rank (§7) — permanent, never season-resets (§7.8).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import ScoringConfig
from app.scoring.types import HabitSpec, Observation


def day_xp(
    scheduled: dict[str, Observation],
    completions: dict[str, float],
    cfg: ScoringConfig,
) -> int:
    """Base XP per qualifying log + bonus XP for exceeding target / bonus-eligible work.

    A "qualifying log" is any target the user actually logged (done, or a positive
    value). Bonus XP for completion beyond target (overtime / S-rank, §7.5) or
    explicitly bonus-eligible (unscheduled) work.
    """
    xp = 0
    for hid, obs in scheduled.items():
        logged = obs.done or (obs.value is not None and obs.value > 0)
        if not logged:
            continue
        xp += cfg.xp_per_log
        comp = completions.get(hid, 0.0)
        if comp > 1.0 or obs.bonus_eligible:
            xp += cfg.xp_bonus_overtime
    return xp


@dataclass(frozen=True)
class LevelState:
    level: int
    xp_into_level: int
    reward_tokens: int  # total tokens unlocked at this level (§8.2)


def level_for_total_xp(total_xp: int, cfg: ScoringConfig) -> LevelState:
    """Increasing curve: advancing from level L to L+1 costs xp_level_base * L (§8.2)."""
    level = 1
    remaining = max(0, total_xp)
    while remaining >= cfg.xp_level_base * level:
        remaining -= cfg.xp_level_base * level
        level += 1
    tokens = level // cfg.reward_token_every_levels
    return LevelState(level=level, xp_into_level=remaining, reward_tokens=tokens)

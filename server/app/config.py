"""Runtime settings and scoring constants.

Two distinct things live here:

* ``Settings`` — environment/secret-backed config (DB URL, later: API keys). Read
  from ``.env``; never hardcode drifting external identifiers (spec §1 rule 1, §24).
* ``ScoringConfig`` — every TUNABLE scoring constant from spec §7–§9, in ONE place.
  Season 1 is a calibration run (spec §25), so these must all be swappable without
  touching engine logic. The scoring engine takes a ``ScoringConfig`` as input and
  reads nothing global — keeping scoring a pure function of ``logs + config`` (§20).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings. Loaded from ``.env`` (see ``.env.example``)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://lifeos:lifeos@localhost:5432/lifeos"


def get_settings() -> Settings:
    return Settings()


@dataclass(frozen=True)
class ScoringConfig:
    """All TUNABLE scoring/progression constants (spec §7–§9), with spec defaults.

    Frozen so a run can't mutate it mid-replay; swap a whole config to recalibrate.
    """

    # --- §7.2 per-habit performance score ---
    completion_cap: float = 1.25          # COMPLETION_CAP
    baseline_window: int = 14             # BASELINE_WINDOW (eligible days)
    pass_line: float = 0.5                # PASS_LINE
    w_abs: float = 0.5                    # W_ABS   (absolute term)
    w_imp: float = 0.35                   # W_IMP   (improvement term)
    w_timing: float = 0.15               # W_TIMING (zeroed when neutralized)
    importance_divisor: float = 3.0       # importance/3 -> 0.33..1.67
    base_lp_swing: float = 15.0           # BASE_LP_SWING

    # --- new-habit grace (§7.2) ---
    new_habit_grace_days: int = 7         # < this many eligible days => gain = max(0, gain)
    # Spec says "a low anchor" for new habits but gives no number (DECISIONS.md).
    new_habit_baseline_anchor: float = 0.0

    # --- §7.3 domain-level equilibrium ---
    decay_rate: float = 0.02              # DECAY_RATE
    lp_floor: float = 0.0                 # FLOOR

    # --- §7.7 tier ladder ---
    lp_per_division: int = 100            # LP_PER_DIVISION
    # Midpoint the season soft-reset compresses toward (§7.8). Iron I..Diamond IV is
    # 7 tiers x 4 divisions x 100 = 2800 LP; midpoint = 1400. TUNABLE (DECISIONS.md).
    ladder_midpoint_lp: float = 1400.0
    # Apex thresholds (single-player => fixed LP, §7.7). Master begins where the
    # divisioned ladder ends (7 tiers x 400). All TUNABLE (DECISIONS.md).
    apex_master_lp: float = 2800.0
    apex_grandmaster_lp: float = 3200.0
    apex_challenger_lp: float = 3600.0

    # --- §7.8 seasons ---
    reset_compression: float = 0.35       # new_lp = MID + (old-MID)*compression

    # --- §8 XP / rewards / forgiveness ---
    xp_per_log: int = 10                  # XP_PER_LOG (any qualifying log)
    xp_bonus_overtime: int = 5            # extra XP when completion exceeds target (§7.5, §8.1)
    # Increasing level curve: XP to advance from level L to L+1 = xp_level_base * L.
    xp_level_base: int = 100              # TUNABLE (spec §8.2 "increasing thresholds")
    reward_token_every_levels: int = 10   # §8.2 reward token cadence
    mulligan_cap_per_month: int = 3       # MULLIGAN_CAP
    mulligan_cost_ladder: tuple[int, ...] = (200, 400, 800)  # escalating cost

    # --- §15 body metrics (present for later phases) ---
    weight_smoothing_days: int = 7        # WEIGHT_SMOOTHING (7-day EMA)


#: Literal-spec constants (§7–§9 defaults). Kept as the reference point; the engine does
#: NOT run on these by default — see ``ACTIVE_SCORING``.
DEFAULT_SCORING = ScoringConfig()

#: The constants the engine actually runs on (Season-1 "active" defaults; DECISIONS.md).
#: Lever A: the literal-spec swing/decay leave a disciplined domain's equilibrium far
#: below the ladder midpoint, which *inverts* the season soft-reset (it would promote
#: instead of demote). Bumping BASE_LP_SWING + DECAY_RATE lands equilibria on the
#: mid/upper ladder so the reset demotes correctly and a perfect ~30 days reclaims peak.
#: These are Season-1 tunables, NOT final — recalibrate after living through one reset.
ACTIVE_SCORING = replace(DEFAULT_SCORING, base_lp_swing=200.0, decay_rate=0.075)

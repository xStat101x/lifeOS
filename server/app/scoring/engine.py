"""Day-close scoring + multi-day replay orchestration (spec §7–§10).

The engine holds the small amount of carried state (per-habit baselines, per-domain LP,
running XP) and processes days in order. Everything it produces is deterministic given
the same inputs + config, and every per-target record is emitted so the ladder is
re-computable (§7.6, §20).

Systems score exactly like quantitative habits (§7.4): pass them in as ``HabitSpec``
with ``is_system=True`` and ``kind='quantitative'`` (value=steps_done, target=steps_total).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.config import ACTIVE_SCORING, ScoringConfig
from app.scoring.baseline import BaselineTracker
from app.scoring.day_modes import resolve_effect
from app.scoring.equilibrium import update_domain_lp
from app.scoring.performance import completion_for, gain_for, performance_score
from app.scoring.seasons import soft_reset_lp
from app.scoring.types import (
    DayMode,
    DayResult,
    DomainDayResult,
    HabitSpec,
    Observation,
    TargetEval,
)
from app.scoring.xp import day_xp


@dataclass
class DayInput:
    day: date
    scheduled: dict[str, Observation]     # habit_id -> observation (scheduled targets only)
    mode: DayMode | None = None


@dataclass
class Engine:
    habits: dict[str, HabitSpec]
    domains: list[str]
    cfg: ScoringConfig = ACTIVE_SCORING
    lp: dict[str, float] = field(default_factory=dict)
    xp_total: int = 0
    _baselines: BaselineTracker = field(init=False)

    def __post_init__(self) -> None:
        self._baselines = BaselineTracker(self.cfg)
        for d in self.domains:
            self.lp.setdefault(d, self.cfg.lp_floor)

    # --- §10 day-close: score one day, mutate carried state ---
    def process_day(self, day_input: DayInput) -> DayResult:
        result = DayResult(day=day_input.day)
        gain_total: dict[str, float] = {d: 0.0 for d in self.domains}
        active: dict[str, int] = {d: 0 for d in self.domains}
        completions: dict[str, float] = {}

        for hid, obs in day_input.scheduled.items():
            spec = self.habits[hid]
            effect = resolve_effect(day_input.mode, spec)
            target_kind = "system" if spec.is_system else "habit"

            if effect.paused:
                # Skipped entirely: no eval, no baseline, no gain, no decay (§7.2/§7.3).
                result.targets.append(
                    TargetEval(habit_id=hid, domain=spec.domain,
                               target_kind=target_kind, was_paused=True)
                )
                continue

            eff_target = (
                spec.target * effect.target_scale if spec.target is not None else None
            )
            completion = completion_for(
                spec.kind, value=obs.value, done=obs.done,
                effective_target=eff_target, cfg=self.cfg,
            )
            completions[hid] = completion

            baseline = self._baselines.completion_baseline(hid)
            is_new = self._baselines.is_new_habit(hid)

            timing_active = spec.has_timing and not effect.timing_neutralized
            if timing_active and obs.timing_in_window is not None:
                timing = 1.0 if obs.timing_in_window else 0.0
                timing_baseline = self._baselines.timing_baseline(hid)
            else:
                timing = None
                timing_baseline = None
                timing_active = False

            perf = performance_score(
                completion=completion, baseline=baseline,
                timing=timing, timing_baseline=timing_baseline,
                timing_active=timing_active, cfg=self.cfg,
            )
            gain = gain_for(
                performance=perf, importance=spec.importance,
                importance_scale=effect.importance_scale,
                is_new_habit=is_new, cfg=self.cfg,
            )

            gain_total[spec.domain] += gain
            active[spec.domain] += 1
            self._baselines.record(hid, completion, timing)

            result.targets.append(TargetEval(
                habit_id=hid, domain=spec.domain, target_kind=target_kind,
                completion=completion, completion_baseline=baseline,
                timing=timing, timing_baseline=timing_baseline,
                performance_score=perf, gain=gain, is_new_habit=is_new,
                importance_effective=spec.importance * effect.importance_scale,
            ))

        # --- §7.3 domain equilibrium update ---
        for d in self.domains:
            upd = update_domain_lp(
                lp_before=self.lp[d], gain_total=gain_total[d],
                active_expectations=active[d], cfg=self.cfg,
            )
            self.lp[d] = upd.lp_after
            result.domains[d] = DomainDayResult(
                domain=d, gain_total=upd.gain_total, decay=upd.decay,
                active_expectations=active[d], lp_before=upd.lp_before,
                lp_after=upd.lp_after,
            )

        # --- §8 XP (never reduced by a bad day) ---
        earned = day_xp(day_input.scheduled, completions, self.cfg)
        self.xp_total += earned
        result.xp_earned = earned
        result.xp_total = self.xp_total
        return result

    def overall_lp(self, weights: dict[str, float] | None = None) -> float:
        """Weighted average of domain LPs (§7.6). Equal weights if none given."""
        w = weights or {d: 1.0 for d in self.domains}
        total_w = sum(w.get(d, 0.0) for d in self.domains)
        if total_w == 0:
            return 0.0
        return sum(self.lp[d] * w.get(d, 0.0) for d in self.domains) / total_w

    def apply_season_reset(self) -> dict[str, float]:
        """Soft-reset every domain toward the midpoint (§7.8). Returns pre-reset peaks."""
        peaks = dict(self.lp)
        for d in self.domains:
            self.lp[d] = soft_reset_lp(self.lp[d], self.cfg)
        return peaks

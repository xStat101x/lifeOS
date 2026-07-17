"""Load DB config + logs and resolve them into pure-engine inputs (spec §6, §9, §11).

``World`` loads everything once, then answers per-day questions the replay needs:
which targets are scheduled, their phase-resolved targets, the active Day Mode, and the
observations implied by that day's logs (a scheduled target with no log is a miss).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from app.models import (
    DayAssignment,
    DayMode as DayModeModel,
    DayModeOverride,
    Domain,
    Habit,
    HabitPhase,
    Log,
    Mulligan,
    Season,
    System,
    SystemStep,
)
from app.scoring.types import (
    DayMode,
    HabitSpec,
    Observation,
    Op,
    Override,
    Scope,
)

# Python weekday() (Mon=0) -> the two-letter codes used in schedule_config / plans.
_WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _in_window(logged_at: datetime, window: dict | None) -> bool | None:
    """Whether a log's wall-clock time falls inside a timing window.

    Phase 1 treats the stored ``logged_at`` clock time as local for timing (the client
    knows local time at capture, §10); a full timezone pass is deferred. If a log's
    ``meta`` carries an explicit ``timing_in_window`` bool, that wins.
    """
    if not window:
        return None
    lt = logged_at.timetz().replace(tzinfo=None) if logged_at.tzinfo else logged_at.time()
    return _parse_hhmm(window["start"]) <= lt <= _parse_hhmm(window["end"])


@dataclass
class World:
    """All scoring-relevant config + logs, loaded once for a replay."""

    domain_key: dict[uuid.UUID, str]
    domain_id_by_key: dict[str, uuid.UUID]
    domain_weight: dict[str, float]
    habits: list[Habit]
    phases_by_habit: dict[uuid.UUID, list[HabitPhase]]
    systems: list[System]
    steps_by_system: dict[uuid.UUID, list[SystemStep]]
    modes_by_id: dict[uuid.UUID, tuple[DayModeModel, list[DayModeOverride]]]
    assignment_by_day: dict[date, uuid.UUID]
    retroactive_days: set[date]           # days whose mode was applied via a paid mulligan
    mulligan_days: set[date]              # days a mulligan was spent on (§8.3)
    seasons: list[Season]
    logs_by_day: dict[date, list[Log]]

    @classmethod
    def load(cls, session: Session, upto: date) -> "World":
        domains = session.query(Domain).filter(Domain.deleted_at.is_(None)).all()
        domain_key = {d.id: d.key for d in domains}
        domain_id_by_key = {d.key: d.id for d in domains}
        domain_weight = {d.key: d.weight for d in domains}

        # Load historical config too. Per-day expectation windows below decide whether a
        # target participates; filtering to today's active rows would rewrite old rank.
        habits = session.query(Habit).all()
        phases_by_habit: dict[uuid.UUID, list[HabitPhase]] = defaultdict(list)
        for p in session.query(HabitPhase).filter(HabitPhase.deleted_at.is_(None)).all():
            phases_by_habit[p.habit_id].append(p)

        systems = session.query(System).all()
        steps_by_system: dict[uuid.UUID, list[SystemStep]] = defaultdict(list)
        for s in session.query(SystemStep).filter(SystemStep.deleted_at.is_(None)).all():
            steps_by_system[s.system_id].append(s)

        modes_by_id: dict[uuid.UUID, tuple[DayModeModel, list[DayModeOverride]]] = {}
        for m in session.query(DayModeModel).filter(DayModeModel.deleted_at.is_(None)).all():
            ovs = (
                session.query(DayModeOverride)
                .filter(DayModeOverride.day_mode_id == m.id,
                        DayModeOverride.deleted_at.is_(None))
                .all()
            )
            modes_by_id[m.id] = (m, ovs)

        assignment_by_day: dict[date, uuid.UUID] = {}
        retroactive_days: set[date] = set()
        for a in (
            session.query(DayAssignment)
            .filter(DayAssignment.deleted_at.is_(None))
            .order_by(DayAssignment.applied_at.is_(None), DayAssignment.applied_at)
            .all()
        ):
            assignment_by_day[a.effective_day] = a.day_mode_id  # last write wins
            if a.is_retroactive:
                retroactive_days.add(a.effective_day)

        mulligan_days = {
            m.effective_day
            for m in session.query(Mulligan)
            .filter(Mulligan.deleted_at.is_(None), Mulligan.effective_day <= upto)
            .all()
        }

        seasons = (
            session.query(Season)
            .filter(Season.deleted_at.is_(None))
            .order_by(Season.start_day)
            .all()
        )

        logs_by_day: dict[date, list[Log]] = defaultdict(list)
        for lg in (
            session.query(Log)
            .filter(Log.deleted_at.is_(None), Log.effective_day <= upto)
            .all()
        ):
            logs_by_day[lg.effective_day].append(lg)

        return cls(
            domain_key=domain_key, domain_id_by_key=domain_id_by_key,
            domain_weight=domain_weight, habits=habits,
            phases_by_habit=phases_by_habit, systems=systems,
            steps_by_system=steps_by_system, modes_by_id=modes_by_id,
            assignment_by_day=assignment_by_day, retroactive_days=retroactive_days,
            mulligan_days=mulligan_days, seasons=seasons, logs_by_day=logs_by_day,
        )

    def has_mulligan(self, day: date) -> bool:
        return day in self.mulligan_days

    def is_retroactive(self, day: date) -> bool:
        return day in self.retroactive_days

    # --- historical expectation windows -------------------------------------------
    @staticmethod
    def _created_day(target: Habit | System) -> date:
        return target.created_at.date()

    @staticmethod
    def _inactive_from(target: Habit | System) -> date | None:
        """First day a currently removed target is no longer expected.

        Phase 1 has timestamped config rows rather than a separate activation ledger:
        soft deletion supplies the removal timestamp, while ``updated_at`` supplies it
        when ``active`` is switched off. The boundary is exclusive.
        """
        if target.deleted_at is not None:
            return target.deleted_at.date()
        if not target.active:
            return target.updated_at.date()
        return None

    def _target_active_on(self, target: Habit | System, day: date) -> bool:
        if day < self._created_day(target):
            return False
        inactive_from = self._inactive_from(target)
        return inactive_from is None or day < inactive_from

    def _habit_expected_on(self, habit: Habit, day: date) -> bool:
        if not self._target_active_on(habit, day) or not self._habit_scheduled(habit, day):
            return False
        # A quantitative habit has no expectation during a gap between target phases.
        return habit.kind != "quantitative" or self._phase_for(habit, day) is not None

    def _system_expected_on(self, system: System, day: date) -> bool:
        return self._target_active_on(system, day)  # systems are daily in Phase 1

    def _first_expectation(self, target: Habit | System, upto: date) -> date | None:
        day = self._created_day(target)
        inactive_from = self._inactive_from(target)
        last = min(upto, inactive_from - date.resolution) if inactive_from else upto
        while day <= last:
            expected = (
                self._habit_expected_on(target, day)
                if isinstance(target, Habit)
                else self._system_expected_on(target, day)
            )
            if expected:
                return day
            day += date.resolution
        return None

    # --- domains actually scored (have >=1 expectation through the replay day) ----
    def scored_domain_keys(self, upto: date) -> list[str]:
        keys = {
            self.domain_key[h.domain_id]
            for h in self.habits
            if self._first_expectation(h, upto) is not None
        }
        keys |= {
            self.domain_key[s.domain_id]
            for s in self.systems
            if self._first_expectation(s, upto) is not None
        }
        return sorted(keys)

    def weights(self, upto: date) -> dict[str, float]:
        return {k: self.domain_weight[k] for k in self.scored_domain_keys(upto)}

    def history_start(self, upto: date) -> date:
        starts = [
            start
            for target in [*self.habits, *self.systems]
            if (start := self._first_expectation(target, upto)) is not None
        ]
        return min(starts) if starts else upto

    def season_for(self, day: date) -> Season | None:
        containing = [s for s in self.seasons if s.start_day <= day <= s.end_day]
        if containing:
            return containing[-1]
        earlier = [s for s in self.seasons if s.start_day <= day]
        return earlier[-1] if earlier else (self.seasons[0] if self.seasons else None)

    # --- scheduling (§11); floating_count is DEFERRED and treated as unscheduled ----
    def _habit_scheduled(self, habit: Habit, day: date) -> bool:
        st = habit.schedule_type
        if st == "daily":
            return True
        if st == "weekdays":
            return day.weekday() < 5
        if st == "specific_days":
            return _WEEKDAY_CODES[day.weekday()] in (habit.schedule_config or {}).get("days", [])
        return False  # 'floating_count' (deferred) or unknown

    def _phase_for(self, habit: Habit, day: date) -> HabitPhase | None:
        for p in self.phases_by_habit.get(habit.id, []):
            if p.effective_from <= day and (p.effective_to is None or p.effective_to >= day):
                return p
        return None

    def _phase_target(self, habit: Habit, day: date) -> float | None:
        phase = self._phase_for(habit, day)
        return phase.target_value if phase is not None else None

    def day_mode(self, day: date) -> DayMode | None:
        mode_id = self.assignment_by_day.get(day)
        if mode_id is None:
            return None
        model, ovs = self.modes_by_id[mode_id]
        overrides = tuple(self._to_override(o) for o in ovs if self._to_override(o))
        return DayMode(name=model.name, overrides=overrides)

    def _to_override(self, o: DayModeOverride) -> Override | None:
        scope = Scope(o.scope)
        if scope == Scope.DOMAIN:
            ref = self.domain_key.get(o.scope_id)
            if ref is None:
                return None
        else:  # habit / system -> string uuid matches HabitSpec.id / system_id
            ref = str(o.scope_id)
        return Override(scope=scope, ref=ref, op=Op(o.op), factor=o.factor, params=o.params)

    # --- specs + observations for a single day -------------------------------------
    def specs_and_obs(self, day: date) -> tuple[dict[str, HabitSpec], dict[str, Observation]]:
        specs: dict[str, HabitSpec] = {}
        obs: dict[str, Observation] = {}
        day_logs = self.logs_by_day.get(day, [])

        # habits scheduled that day
        for h in self.habits:
            if not self._habit_expected_on(h, day):
                continue
            hid = str(h.id)
            specs[hid] = HabitSpec(
                id=hid, domain=self.domain_key[h.domain_id], importance=h.importance,
                kind=h.kind, has_timing=h.timing_window is not None,
                target=self._phase_target(h, day),
            )
            obs[hid] = self._habit_obs(h, day_logs)

        # Systems are scheduled daily inside their historical expectation window.
        for s in self.systems:
            if not self._system_expected_on(s, day):
                continue
            sid = str(s.id)
            steps = self.steps_by_system.get(s.id, [])
            specs[sid] = HabitSpec(
                id=sid, domain=self.domain_key[s.domain_id], importance=s.importance,
                kind="quantitative", has_timing=s.timing_window is not None,
                target=float(len(steps)) if steps else None,
                is_system=True, system_id=sid,
            )
            obs[sid] = self._system_obs(s, steps, day_logs)

        return specs, obs

    def _habit_obs(self, h: Habit, day_logs: list[Log]) -> Observation:
        mine = [lg for lg in day_logs if lg.target_kind == "habit" and lg.target_id == h.id]
        if not mine:
            return Observation()  # scheduled but not logged -> miss (completion 0)
        timing = None
        if h.timing_window is not None:
            latest = max(mine, key=lambda lg: lg.logged_at)
            explicit = (latest.meta or {}).get("timing_in_window")
            timing = explicit if isinstance(explicit, bool) else _in_window(
                latest.logged_at, h.timing_window
            )
        if h.kind == "quantitative":
            total = sum(lg.value for lg in mine if lg.value is not None)
            return Observation(value=total, timing_in_window=timing)
        return Observation(done=True, timing_in_window=timing)

    def _system_obs(self, s: System, steps: list[SystemStep], day_logs: list[Log]) -> Observation:
        step_ids = {st.id for st in steps}
        step_logs = [
            lg for lg in day_logs
            if lg.target_kind == "system_step" and lg.target_id in step_ids
        ]
        # allow a direct 'system' log carrying steps_done in value
        sys_logs = [lg for lg in day_logs
                    if lg.target_kind == "system" and lg.target_id == s.id]
        if not step_logs and not sys_logs:
            return Observation()  # miss
        if sys_logs:
            done_count = max((lg.value or 0) for lg in sys_logs)
        else:
            done_count = len({lg.target_id for lg in step_logs})
        timing = None
        if s.timing_window is not None and (step_logs or sys_logs):
            latest = max(step_logs + sys_logs, key=lambda lg: lg.logged_at)
            explicit = (latest.meta or {}).get("timing_in_window")
            timing = explicit if isinstance(explicit, bool) else _in_window(
                latest.logged_at, s.timing_window
            )
        return Observation(value=float(done_count), timing_in_window=timing)

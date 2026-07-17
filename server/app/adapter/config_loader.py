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
    seasons: list[Season]
    logs_by_day: dict[date, list[Log]]

    @classmethod
    def load(cls, session: Session, upto: date) -> "World":
        domains = session.query(Domain).filter(Domain.deleted_at.is_(None)).all()
        domain_key = {d.id: d.key for d in domains}
        domain_id_by_key = {d.key: d.id for d in domains}
        domain_weight = {d.key: d.weight for d in domains}

        habits = (
            session.query(Habit)
            .filter(Habit.active.is_(True), Habit.deleted_at.is_(None))
            .all()
        )
        phases_by_habit: dict[uuid.UUID, list[HabitPhase]] = defaultdict(list)
        for p in session.query(HabitPhase).filter(HabitPhase.deleted_at.is_(None)).all():
            phases_by_habit[p.habit_id].append(p)

        systems = (
            session.query(System)
            .filter(System.active.is_(True), System.deleted_at.is_(None))
            .all()
        )
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
        for a in (
            session.query(DayAssignment)
            .filter(DayAssignment.deleted_at.is_(None))
            .order_by(DayAssignment.applied_at.is_(None), DayAssignment.applied_at)
            .all()
        ):
            assignment_by_day[a.effective_day] = a.day_mode_id  # last write wins

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
            assignment_by_day=assignment_by_day, seasons=seasons,
            logs_by_day=logs_by_day,
        )

    # --- domains actually scored (have >=1 active habit or system) -------------
    def scored_domain_keys(self) -> list[str]:
        keys = {self.domain_key[h.domain_id] for h in self.habits}
        keys |= {self.domain_key[s.domain_id] for s in self.systems}
        return sorted(keys)

    def weights(self) -> dict[str, float]:
        return {k: self.domain_weight[k] for k in self.scored_domain_keys()}

    def history_start(self, upto: date) -> date:
        logged = [d for d in self.logs_by_day if d <= upto]
        return min(logged) if logged else upto

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

    def _phase_target(self, habit: Habit, day: date) -> float | None:
        for p in self.phases_by_habit.get(habit.id, []):
            if p.effective_from <= day and (p.effective_to is None or p.effective_to >= day):
                return p.target_value
        return None

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
            if not self._habit_scheduled(h, day):
                continue
            hid = str(h.id)
            specs[hid] = HabitSpec(
                id=hid, domain=self.domain_key[h.domain_id], importance=h.importance,
                kind=h.kind, has_timing=h.timing_window is not None,
                target=self._phase_target(h, day),
            )
            obs[hid] = self._habit_obs(h, day_logs)

        # active systems are scheduled daily (Phase 1 assumption)
        for s in self.systems:
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

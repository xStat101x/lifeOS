"""Rolling baselines + habit age (spec §7.2).

baseline = mean completion over the last BASELINE_WINDOW *eligible* days (paused/Away
days never enter history). New habits (< grace-window eligible days) use a low anchor,
so early completions are strong wins and early misses can't corrupt a real baseline.

Ordering contract: for a given day, read the baseline/age FIRST (reflecting prior days
only), compute the score, THEN ``record`` today's completion.
"""

from __future__ import annotations

from collections import deque

from app.config import ScoringConfig


class BaselineTracker:
    def __init__(self, cfg: ScoringConfig) -> None:
        self._cfg = cfg
        self._completions: dict[str, deque[float]] = {}
        self._timings: dict[str, deque[float]] = {}
        self._age: dict[str, int] = {}  # count of eligible days recorded

    def _comp(self, habit_id: str) -> deque[float]:
        return self._completions.setdefault(
            habit_id, deque(maxlen=self._cfg.baseline_window)
        )

    def _tim(self, habit_id: str) -> deque[float]:
        return self._timings.setdefault(
            habit_id, deque(maxlen=self._cfg.baseline_window)
        )

    def age(self, habit_id: str) -> int:
        """Eligible days seen so far (before today)."""
        return self._age.get(habit_id, 0)

    def is_new_habit(self, habit_id: str) -> bool:
        return self.age(habit_id) < self._cfg.new_habit_grace_days

    def completion_baseline(self, habit_id: str) -> float:
        if self.is_new_habit(habit_id):
            return self._cfg.new_habit_baseline_anchor
        hist = self._comp(habit_id)
        return sum(hist) / len(hist) if hist else self._cfg.new_habit_baseline_anchor

    def timing_baseline(self, habit_id: str) -> float:
        hist = self._tim(habit_id)
        return sum(hist) / len(hist) if hist else 0.0

    def record(self, habit_id: str, completion: float, timing: float | None) -> None:
        """Append an eligible (scored, non-paused) day. Paused days must NOT be recorded."""
        self._comp(habit_id).append(completion)
        if timing is not None:
            self._tim(habit_id).append(timing)
        self._age[habit_id] = self._age.get(habit_id, 0) + 1

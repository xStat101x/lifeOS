"""Aggregates every ORM model so ``Base.metadata`` is fully populated (Alembic
autogenerate + create_all both rely on this single import surface)."""

from app.models.base import Base
from app.models.identity import Domain, User
from app.models.habits import Habit, HabitPhase, System, SystemStep
from app.models.logs import Log
from app.models.day_modes import (
    DayAssignment,
    DayMode,
    DayModeOverride,
    DayModeReminder,
)
from app.models.scoring import (
    AccountLevel,
    DayEvaluation,
    Mulligan,
    RankPeak,
    RankState,
    Reward,
    Season,
    XPLedger,
)
from app.models.fitness import (
    CardioSession,
    Exercise,
    LiftPlan,
    LiftPlanEntry,
    LiftSet,
)
from app.models.body import WeightEntry
from app.models.nutrition import Meal, MealTemplate
from app.models.calendar import CalendarCache, LifeosBlock, Task
from app.models.finance import FinBudget, FinSnapshot, FinTransaction

__all__ = [
    "Base",
    "User",
    "Domain",
    "Habit",
    "HabitPhase",
    "System",
    "SystemStep",
    "Log",
    "DayMode",
    "DayModeOverride",
    "DayModeReminder",
    "DayAssignment",
    "Season",
    "RankPeak",
    "DayEvaluation",
    "RankState",
    "XPLedger",
    "AccountLevel",
    "Reward",
    "Mulligan",
    "Exercise",
    "LiftPlan",
    "LiftPlanEntry",
    "LiftSet",
    "CardioSession",
    "WeightEntry",
    "Meal",
    "MealTemplate",
    "CalendarCache",
    "LifeosBlock",
    "Task",
    "FinTransaction",
    "FinBudget",
    "FinSnapshot",
]

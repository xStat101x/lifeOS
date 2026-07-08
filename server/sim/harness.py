"""Simulation harness — feed day-by-day logs, print rank + XP over time (spec §23 step 4).

Run it directly for a narrated demo:

    python -m sim.harness
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config import ACTIVE_SCORING, ScoringConfig
from app.scoring.engine import DayInput, Engine
from app.scoring.ladder import lp_to_rank
from sim.scenarios import build_world, days, make_day


@dataclass
class Snapshot:
    day: date
    domain_lp: dict[str, float]
    overall_lp: float
    overall_rank: str
    xp_total: int
    xp_earned: int


def simulate(engine: Engine, day_inputs: list[DayInput],
             weights: dict[str, float] | None = None) -> list[Snapshot]:
    snaps: list[Snapshot] = []
    for di in day_inputs:
        r = engine.process_day(di)
        overall = engine.overall_lp(weights)
        snaps.append(Snapshot(
            day=di.day,
            domain_lp=dict(engine.lp),
            overall_lp=overall,
            overall_rank=lp_to_rank(overall, engine.cfg).label(),
            xp_total=r.xp_total,
            xp_earned=r.xp_earned,
        ))
    return snaps


def print_history(snaps: list[Snapshot], *, every: int = 1) -> None:
    if not snaps:
        return
    domains = list(snaps[0].domain_lp)
    header = f"{'day':>4}  " + "  ".join(f"{d[:4]:>6}" for d in domains)
    header += f"  {'overall':>8}  {'rank':>14}  {'xp':>7}"
    print(header)
    print("-" * len(header))
    for i, s in enumerate(snaps):
        if i % every and i != len(snaps) - 1:
            continue
        row = f"{i:>4}  " + "  ".join(f"{s.domain_lp[d]:>6.0f}" for d in domains)
        row += f"  {s.overall_lp:>8.0f}  {s.overall_rank:>14}  {s.xp_total:>7}"
        print(row)


def _demo(cfg: ScoringConfig = ACTIVE_SCORING) -> None:
    habits, domains, weights = build_world()
    eng = Engine(habits=habits, domains=domains, cfg=cfg)
    start = date(2026, 8, 20)
    seq = days(start, 120)
    inputs = []
    for i, d in enumerate(seq):
        if i < 70:
            frac = 1.0                     # 70 disciplined days
        elif i < 90:
            frac = 0.3                     # a 20-day slump
        else:
            frac = 1.05                    # recover, slightly overachieving
        inputs.append(make_day(habits, d, frac))
    snaps = simulate(eng, inputs, weights)
    print("LifeOS scoring simulation — 70 perfect / 20 slump / 30 recover\n")
    print_history(snaps, every=10)


if __name__ == "__main__":
    _demo()

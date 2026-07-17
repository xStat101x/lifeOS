"""Deterministic day-close: replay history -> target day, persist the results (§10, §20).

Because the engine carries baseline/LP/XP state across days, a correct close for day D
replays every day from the first log through D, reconstructing all state purely from
``logs + config``. The persisted rows are therefore a *cache* of that replay:
re-running a close recomputes and overwrites the same values (idempotent), and the whole
ladder stays re-computable from ``logs`` alone (§20 invariant 4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.adapter.config_loader import World
from app.config import ACTIVE_SCORING, ScoringConfig
from app.models import AccountLevel, DayEvaluation, RankPeak, RankState, Season, XPLedger
from app.scoring.engine import DayInput, Engine
from app.scoring.ladder import lp_to_rank
from app.scoring.xp import level_for_total_xp


@dataclass
class DayCloseResult:
    day: date
    domains: dict[str, dict]      # key -> {lp, tier, division, label}
    overall: dict                 # {lp, tier, division, label}
    xp_earned: int
    xp_total: int
    level: int


def _replay(world: World, cfg: ScoringConfig, upto: date):
    """Replay history_start..upto.

    Returns (engine, day_result_for_upto, weights, peaks). ``peaks`` is the running
    high-water LP per (season_id, scope, domain-key-or-None), captured day-by-day so the
    pre-reset peak of an ending season is banked exactly as the replay crosses it (§7.8) —
    not re-derived on the fly, so it stays correct even if replay is later optimized.
    """
    domains = world.scored_domain_keys()
    weights = world.weights()
    eng = Engine(habits={}, domains=domains, cfg=cfg)
    peaks: dict[tuple, float] = {}

    day = world.history_start(upto)
    prev_season: Season | None = None
    result_for_day = None
    while day <= upto:
        season = world.season_for(day)
        if season is not None and prev_season is not None and season.id != prev_season.id:
            eng.apply_season_reset()  # §7.8 soft reset at a season boundary
        prev_season = season

        specs, obs = world.specs_and_obs(day)
        eng.habits = specs  # per-day specs carry that day's phase targets (§11)
        res = eng.process_day(DayInput(day=day, scheduled=obs, mode=world.day_mode(day)))

        if season is not None:  # bank the day's LP into the season's running peak
            for dkey in eng.domains:
                k = (season.id, "domain", dkey)
                peaks[k] = max(peaks.get(k, eng.lp[dkey]), eng.lp[dkey])
            overall = eng.overall_lp(weights)
            ok = (season.id, "overall", None)
            peaks[ok] = max(peaks.get(ok, overall), overall)

        if day == upto:
            result_for_day = res
        day += timedelta(days=1)

    return eng, result_for_day, weights, peaks


def close_day(session: Session, day: date, cfg: ScoringConfig = ACTIVE_SCORING) -> DayCloseResult:
    world = World.load(session, upto=day)
    eng, result, weights, peaks = _replay(world, cfg, day)
    season = world.season_for(day)
    if season is None:
        raise ValueError(f"No season covers {day}; cannot persist rank_state.")

    now = datetime.now(timezone.utc)
    mode_id = world.assignment_by_day.get(day)

    # --- day_evaluations: recomputable cache -> hard-replace this day's rows ---
    session.query(DayEvaluation).filter(DayEvaluation.effective_day == day).delete()
    for t in (result.targets if result else []):
        dd = result.domains.get(t.domain)
        session.add(DayEvaluation(
            effective_day=day, target_kind=t.target_kind,
            target_id=uuid.UUID(t.habit_id),
            domain_id=world.domain_id_by_key[t.domain],
            completion=t.completion, completion_baseline=t.completion_baseline,
            timing=t.timing, timing_baseline=t.timing_baseline,
            performance_score=t.performance_score, gain=t.gain,
            # domain-level decay/lp_change replicated onto each of the domain's rows
            decay=(dd.decay if dd else None),
            lp_change=(dd.lp_change if dd else None),
            applied_mode_id=mode_id, was_paused=t.was_paused, computed_at=now,
        ))

    # --- rank_state: per-domain + overall for the season (upsert) ---
    domains_out: dict[str, dict] = {}
    for dkey in eng.domains:
        rank = lp_to_rank(eng.lp[dkey], cfg)
        _upsert_rank(session, "domain", world.domain_id_by_key[dkey], season.id,
                     eng.lp[dkey], rank)
        domains_out[dkey] = _rank_dict(eng.lp[dkey], rank)
    overall_lp = eng.overall_lp(weights)
    overall_rank = lp_to_rank(overall_lp, cfg)
    _upsert_rank(session, "overall", None, season.id, overall_lp, overall_rank)

    # --- XP: one idempotent ledger row per day + account_level (never reset, §8) ---
    xp_earned = result.xp_earned if result else 0
    xp_total = result.xp_total if result else 0
    session.query(XPLedger).filter(
        XPLedger.effective_day == day, XPLedger.event == "day_close"
    ).delete()
    session.add(XPLedger(event="day_close", xp_delta=xp_earned,
                         balance=xp_total, effective_day=day))
    lvl = level_for_total_xp(xp_total, cfg)
    account = session.query(AccountLevel).first()
    if account is None:
        session.add(AccountLevel(level=lvl.level, xp_into_level=lvl.xp_into_level))
    else:
        account.level = lvl.level
        account.xp_into_level = lvl.xp_into_level

    # --- rank_peaks: bank each season's high-water mark per scope (§7.8) ---
    for (season_id, scope, dkey), peak_lp in peaks.items():
        scope_id = None if scope == "overall" else world.domain_id_by_key[dkey]
        _upsert_peak(session, season_id, scope, scope_id, peak_lp, cfg)

    session.commit()
    return DayCloseResult(
        day=day, domains=domains_out, overall=_rank_dict(overall_lp, overall_rank),
        xp_earned=xp_earned, xp_total=xp_total, level=lvl.level,
    )


def _rank_dict(lp: float, rank) -> dict:
    return {"lp": round(lp, 2), "tier": rank.tier, "division": rank.division,
            "label": rank.label()}


def _upsert_peak(session: Session, season_id, scope: str, scope_id, peak_lp: float,
                 cfg: ScoringConfig) -> None:
    """Bank the season high-water LP for a scope. Monotonic (never lowers an existing
    peak), so out-of-order closes can't erase a banked peak; a full recompute from wiped
    logs reproduces the true max."""
    q = session.query(RankPeak).filter(RankPeak.season_id == season_id,
                                       RankPeak.scope == scope)
    q = q.filter(RankPeak.scope_id.is_(None)) if scope_id is None \
        else q.filter(RankPeak.scope_id == scope_id)
    rp = q.first()
    final = peak_lp if rp is None else max(rp.peak_lp, peak_lp)
    rank = lp_to_rank(final, cfg)
    if rp is None:
        session.add(RankPeak(season_id=season_id, scope=scope, scope_id=scope_id,
                             peak_lp=final, peak_tier=rank.tier, peak_division=rank.division))
    else:
        rp.peak_lp, rp.peak_tier, rp.peak_division = final, rank.tier, rank.division


def _upsert_rank(session: Session, scope: str, scope_id, season_id, lp: float, rank) -> None:
    q = session.query(RankState).filter(RankState.scope == scope,
                                        RankState.season_id == season_id)
    q = q.filter(RankState.scope_id.is_(None)) if scope_id is None \
        else q.filter(RankState.scope_id == scope_id)
    rs = q.first()
    if rs is None:
        session.add(RankState(scope=scope, scope_id=scope_id, season_id=season_id,
                              lp=lp, tier=rank.tier, division=rank.division))
    else:
        rs.lp, rs.tier, rs.division = lp, rank.tier, rank.division

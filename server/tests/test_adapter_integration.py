"""End-to-end adapter tests against the lifeos-db container (spec §10, §20).

log events -> close day -> read back rank/XP; idempotent re-close; recompute purely
from logs. Uses the seeded config in the throwaway lifeos_test DB (see conftest).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.adapter.config_loader import World
from app.models import (
    DayEvaluation,
    Domain,
    Habit,
    RankPeak,
    RankState,
    Season,
    System,
    User,
    XPLedger,
)

DAY = "2026-08-20"       # inside Season 1 (2026-08-20..2026-11-20)
DAY_D = date(2026, 8, 20)


def _habit_id(db, name: str) -> str:
    return str(db.query(Habit).filter(Habit.name == name).one().id)


def _domain_id(db, key: str):
    return db.query(Domain).filter(Domain.key == key).one().id


def _log_full_nutrition(client, db, day: str = DAY) -> None:
    client.post("/logs", json={"target_kind": "habit", "target_id": _habit_id(db, "Protein target"),
                               "value": 160, "unit": "g", "effective_day": day})
    client.post("/logs", json={"target_kind": "habit", "target_id": _habit_id(db, "Calorie target"),
                               "value": 2800, "unit": "kcal", "effective_day": day})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_log_close_read_roundtrip(client, db):
    r = client.post("/logs", json={
        "target_kind": "habit", "target_id": _habit_id(db, "Protein target"),
        "value": 160, "unit": "g", "effective_day": DAY})
    assert r.status_code == 201
    client.post("/logs", json={
        "target_kind": "habit", "target_id": _habit_id(db, "Calorie target"),
        "value": 2800, "unit": "kcal", "effective_day": DAY})

    close = client.post(f"/day-close/{DAY}").json()
    assert close["domains"]["nutrition"]["lp"] > 0        # hitting targets earns LP
    assert close["xp_total"] == 20                        # two qualifying logs * XP_PER_LOG

    rank = client.get("/rank").json()
    assert rank["overall"] is not None
    assert rank["domains"]["nutrition"]["lp"] == close["domains"]["nutrition"]["lp"]
    assert rank["xp"]["total"] == 20


def test_scheduled_but_unlogged_is_a_miss_not_absent(client, db):
    # Only protein logged; calories is scheduled daily -> it must be scored as a miss.
    client.post("/logs", json={"target_kind": "habit", "target_id": _habit_id(db, "Protein target"),
                               "value": 160, "unit": "g", "effective_day": DAY})
    client.post(f"/day-close/{DAY}")
    db.expire_all()
    kinds = {(e.target_id, e.was_paused) for e in
             db.query(DayEvaluation).filter(DayEvaluation.effective_day == DAY_D).all()}
    # both nutrition habits produced an evaluation row (calories missed, not skipped)
    ids = {tid for tid, _ in kinds}
    assert _habit_id(db, "Protein target") in {str(i) for i in ids}
    assert _habit_id(db, "Calorie target") in {str(i) for i in ids}


def test_day_close_is_idempotent(client, db):
    _log_full_nutrition(client, db)
    first = client.post(f"/day-close/{DAY}").json()
    second = client.post(f"/day-close/{DAY}").json()
    assert first == second                                # identical result

    db.expire_all()
    assert db.query(XPLedger).filter(XPLedger.effective_day == DAY_D).count() == 1
    n_eval = db.query(DayEvaluation).filter(DayEvaluation.effective_day == DAY_D).count()
    client.post(f"/day-close/{DAY}")                      # third close
    db.expire_all()
    assert db.query(DayEvaluation).filter(DayEvaluation.effective_day == DAY_D).count() == n_eval


def test_recomputable_from_logs_only(client, db):
    _log_full_nutrition(client, db)
    before = client.post(f"/day-close/{DAY}").json()

    # wipe the persisted cache, keep the logs, recompute
    db.query(DayEvaluation).delete()
    db.query(RankState).delete()
    db.query(XPLedger).delete()
    db.commit()

    after = client.post(f"/day-close/{DAY}").json()
    assert after["domains"]["nutrition"]["lp"] == before["domains"]["nutrition"]["lp"]
    assert after["overall"]["lp"] == before["overall"]["lp"]
    assert after["xp_total"] == before["xp_total"]


def test_multiple_days_accumulate(client, db):
    _log_full_nutrition(client, db, "2026-08-20")
    lp1 = client.post("/day-close/2026-08-20").json()["domains"]["nutrition"]["lp"]
    _log_full_nutrition(client, db, "2026-08-21")
    close2 = client.post("/day-close/2026-08-21").json()
    assert close2["domains"]["nutrition"]["lp"] > lp1     # two perfect days > one
    assert close2["xp_total"] == 40                       # 4 logs across 2 days


def test_replay_respects_target_expectation_windows(client, db):
    """Adding/removing config cannot rewrite rank before that change took effect."""
    start = date(2026, 8, 20)
    for i in range(10):
        _log_full_nutrition(client, db, (start + timedelta(days=i)).isoformat())
    through = date(2026, 8, 29)
    before = client.post(f"/day-close/{through.isoformat()}").json()

    nutrition = db.query(Domain).filter(Domain.key == "nutrition").one()
    user = db.query(User).first()
    future = Habit(
        user_id=user.id,
        domain_id=nutrition.id,
        name="Future habit",
        kind="binary",
        importance=5,
        schedule_type="daily",
        schedule_config={},
        timing_window=None,
        is_lifelong=True,
        active=True,
        created_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    calories = db.query(Habit).filter(Habit.name == "Calorie target").one()
    calories_original = (calories.active, calories.updated_at)
    calories.active = False
    calories.updated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    db.add(future)
    db.commit()
    try:
        after = client.post(f"/day-close/{through.isoformat()}").json()
        assert after["domains"]["nutrition"]["lp"] == before["domains"]["nutrition"]["lp"]

        db.expire_all()
        target_ids = {
            e.target_id
            for e in db.query(DayEvaluation)
            .filter(DayEvaluation.effective_day == through)
            .all()
        }
        assert calories.id in target_ids      # deactivation tomorrow does not erase history
        assert future.id not in target_ids    # creation tomorrow does not backfill misses
    finally:
        calories.active, calories.updated_at = calories_original
        db.delete(future)
        db.commit()


def test_replay_starts_at_earliest_expectation_without_a_log(db):
    """Silent scheduled days are still part of deterministic replay history."""
    expected_from = date(2026, 8, 15)
    seeded_from = datetime(2026, 8, 20, tzinfo=timezone.utc)
    targets = [*db.query(Habit).all(), *db.query(System).all()]
    originals = [(target, target.created_at, target.updated_at) for target in targets]
    for target in targets:
        target.created_at = seeded_from
        target.updated_at = seeded_from

    routines = db.query(Domain).filter(Domain.key == "routines").one()
    silent = Habit(
        user_id=db.query(User).first().id,
        domain_id=routines.id,
        name="Silent expectation",
        kind="binary",
        importance=3,
        schedule_type="daily",
        schedule_config={},
        timing_window=None,
        is_lifelong=True,
        active=True,
        created_at=datetime.combine(expected_from, time.min, tzinfo=timezone.utc),
        updated_at=datetime.combine(expected_from, time.min, tzinfo=timezone.utc),
    )
    db.add(silent)
    db.commit()
    try:
        world = World.load(db, upto=DAY_D)
        assert world.history_start(DAY_D) == expected_from
    finally:
        db.delete(silent)
        for target, created_at, updated_at in originals:
            target.created_at = created_at
            target.updated_at = updated_at
        db.commit()


def test_season_reset_banks_peak_and_survives_recompute(client, db):
    # Reconfigure into two adjacent seasons so a replay crosses a boundary.
    a_start, a_end = date(2026, 8, 20), date(2026, 9, 28)   # 40 days, climbs above midpoint
    b_start = date(2026, 9, 29)
    db.query(RankState).delete()
    db.query(RankPeak).delete()
    db.query(Season).delete()
    season_a = Season(name="Season A", start_day=a_start, end_day=a_end, reset_compression=0.35)
    season_b = Season(name="Season B", start_day=b_start, end_day=date(2026, 11, 15),
                      reset_compression=0.35)
    db.add_all([season_a, season_b])
    # This synthetic season starts the targets too; earlier silent expectations would
    # correctly count as misses and obscure the reset/peak behavior this test isolates.
    activation = datetime.combine(a_start, time.min, tzinfo=timezone.utc)
    targets = db.query(Habit).join(Domain, Habit.domain_id == Domain.id).filter(
        Domain.key == "nutrition"
    ).all()
    originals = [(target, target.created_at, target.updated_at) for target in targets]
    for target in targets:
        target.created_at = activation
        target.updated_at = activation
    db.commit()
    try:
        a_id, nutrition_id = season_a.id, _domain_id(db, "nutrition")

        # Build a Season-A nutrition peak with sustained perfect logging, then one Season-B day.
        d = a_start
        while d <= a_end:
            _log_full_nutrition(client, db, d.isoformat())
            d += timedelta(days=1)
        _log_full_nutrition(client, db, b_start.isoformat())

        close = client.post(f"/day-close/{b_start.isoformat()}").json()
        db.expire_all()
        peak = db.query(RankPeak).filter(
            RankPeak.season_id == a_id, RankPeak.scope == "domain",
            RankPeak.scope_id == nutrition_id,
        ).one()

        # Banked the PRE-reset high-water mark: above the midpoint the reset compressed from,
        # and above the post-reset Season-B LP.
        assert peak.peak_lp > 1400                                  # a genuine peak, above midpoint
        assert peak.peak_lp > close["domains"]["nutrition"]["lp"]   # reset demoted below it
        banked = peak.peak_lp

        # Wipe the whole cache (incl. rank_peaks) and re-close: peak re-derived identically.
        for model in (DayEvaluation, RankState, XPLedger, RankPeak):
            db.query(model).delete()
        db.commit()
        client.post(f"/day-close/{b_start.isoformat()}")
        db.expire_all()
        peak2 = db.query(RankPeak).filter(
            RankPeak.season_id == a_id, RankPeak.scope == "domain",
            RankPeak.scope_id == nutrition_id,
        ).one()
        assert peak2.peak_lp == banked
    finally:
        for target, created_at, updated_at in originals:
            target.created_at = created_at
            target.updated_at = updated_at
        db.commit()

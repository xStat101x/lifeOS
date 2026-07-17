"""Mulligan spend over the API (spec §8.3, CLAUDE.md invariant 3). Runs against the
lifeos-db container. Covers: neutralize a losing day, monthly cap blocks the 4th,
retroactive mode succeeds only when paid and never becomes a win, insufficient XP, and
recompute-from-source (logs + mulligans)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models import DayEvaluation, DayMode, Habit, Log, RankState, User, XPLedger


def _pin_today(client, d: date) -> None:
    from app.api.main import get_today
    client.app.dependency_overrides[get_today] = lambda: d


def _mode_id(db, name: str) -> str:
    return str(db.query(DayMode).filter(DayMode.name == name).one().id)


def _ids(db) -> dict:
    return {h.name: h.id for h in db.query(Habit).all()}


def _seed_day(db, ids, user_id, day: date, *, protein=160, calories=2800,
              wake=True, brush=True) -> None:
    ts = datetime.combine(day, time(8, 0), tzinfo=timezone.utc)

    def add(name, value=None):
        db.add(Log(user_id=user_id, target_kind="habit", target_id=ids[name],
                   value=value, logged_at=ts, effective_day=day, source="manual", meta={}))

    add("Protein target", protein)
    add("Calorie target", calories)
    if wake:
        add("Wake time")
    if brush:
        add("Brush teeth (PM)")


def _seed_range(db, start: date, n: int, **kw) -> None:
    ids = _ids(db)
    user_id = db.query(User).first().id
    for i in range(n):
        _seed_day(db, ids, user_id, start + timedelta(days=i), **kw)
    db.commit()


def _nutrition_lp(client) -> float:
    return client.get("/rank").json()["domains"]["nutrition"]["lp"]


# 1 --------------------------------------------------------------------------------
def test_neutralize_erases_a_losing_day(client, db):
    _pin_today(client, date(2026, 9, 15))
    _seed_range(db, date(2026, 8, 20), 17)                 # perfect, exits grace
    client.post("/day-close/2026-09-05")
    lp_good = _nutrition_lp(client)

    # 2026-09-06 logged nothing -> nutrition misses -> a real loss (past grace)
    client.post("/day-close/2026-09-06")
    lp_missed = _nutrition_lp(client)
    assert lp_missed < lp_good

    spend = client.post("/mulligans", json={"effective_day": "2026-09-06"})
    assert spend.status_code == 201
    body = spend.json()
    assert body["kind"] == "neutralize" and body["xp_cost"] == 200

    # loss erased: back to the pre-miss LP, never above it
    assert _nutrition_lp(client) == pytest.approx(lp_good, abs=0.01)
    xp = client.get("/rank").json()["xp"]
    assert xp["total"] == 17 * 40                           # lifetime earned unchanged
    assert xp["spendable"] == 17 * 40 - 200                 # only spendable dropped


# 2 --------------------------------------------------------------------------------
def test_monthly_cap_blocks_the_fourth(client, db):
    _pin_today(client, date(2026, 10, 1))
    _seed_range(db, date(2026, 8, 20), 30, protein=200, calories=3500)  # ~50 XP/day => 1500
    client.post("/day-close/2026-09-18")
    assert client.get("/rank").json()["xp"]["spendable"] >= 1400

    costs = []
    for day in ("2026-09-10", "2026-09-11", "2026-09-12"):
        r = client.post("/mulligans", json={"effective_day": day})
        assert r.status_code == 201
        costs.append(r.json()["xp_cost"])
    assert costs == [200, 400, 800]                         # escalating ladder

    fourth = client.post("/mulligans", json={"effective_day": "2026-09-13"})
    assert fourth.status_code == 409
    assert "cap" in fourth.json()["detail"].lower()


# 3 --------------------------------------------------------------------------------
def test_retroactive_mode_only_when_paid_and_never_a_win(client, db):
    _pin_today(client, date(2026, 9, 15))
    _seed_range(db, date(2026, 8, 20), 17)                 # baseline high
    client.post("/day-close/2026-09-05")
    lp_good = _nutrition_lp(client)

    # 2026-09-06: only 96 g protein (0.6x target), calories missed -> a losing day
    ids, user_id = _ids(db), db.query(User).first().id
    _seed_day(db, ids, user_id, date(2026, 9, 6), protein=96, calories=None,
              wake=False, brush=False)
    db.commit()
    client.post("/day-close/2026-09-06")
    lp_missed = _nutrition_lp(client)

    # retroactive mode is refused without a mulligan
    travel = _mode_id(db, "Travel")
    direct = client.post("/day-assignments",
                         json={"effective_day": "2026-09-06", "day_mode_id": travel})
    assert direct.status_code == 409

    # paid: Travel scales protein x0.6 so 96 g now "meets" target -> would be a win,
    # but the mulligan clamps the day to at most neutral.
    paid = client.post("/mulligans", json={"effective_day": "2026-09-06", "mode_id": travel})
    assert paid.status_code == 201
    assert paid.json()["kind"] == "retroactive_mode"

    lp_after = _nutrition_lp(client)
    assert lp_after <= lp_good + 1e-6         # NEVER exceeds the pre-day LP (never a win)
    assert lp_after > lp_missed               # but it did reduce the loss (forgiveness)


# 4 --------------------------------------------------------------------------------
def test_insufficient_xp_rejected(client, db):
    _pin_today(client, date(2026, 9, 15))
    _seed_range(db, date(2026, 8, 20), 2)                  # only ~80 XP
    client.post("/day-close/2026-08-21")

    r = client.post("/mulligans", json={"effective_day": "2026-08-22"})
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"].lower()


# 5 --------------------------------------------------------------------------------
def test_today_or_future_is_not_a_mulligan(client, db):
    _pin_today(client, date(2026, 9, 15))
    _seed_range(db, date(2026, 8, 20), 10)
    client.post("/day-close/2026-08-29")
    # 2026-09-15 is "today" -> mulligan is the wrong tool (apply a mode for free instead)
    r = client.post("/mulligans", json={"effective_day": "2026-09-15"})
    assert r.status_code == 422


# 6 --------------------------------------------------------------------------------
def test_mulligan_survives_cache_wipe_recompute(client, db):
    _pin_today(client, date(2026, 9, 15))
    _seed_range(db, date(2026, 8, 20), 17)
    client.post("/day-close/2026-09-05")
    lp_good = _nutrition_lp(client)
    client.post("/day-close/2026-09-06")                   # miss day
    client.post("/mulligans", json={"effective_day": "2026-09-06"})
    assert _nutrition_lp(client) == pytest.approx(lp_good, abs=0.01)

    # wipe the recomputable cache (keep logs + mulligans), re-close -> forgiveness reappears
    for model in (DayEvaluation, RankState, XPLedger):
        db.query(model).delete()
    db.commit()
    client.post("/day-close/2026-09-06")
    assert _nutrition_lp(client) == pytest.approx(lp_good, abs=0.01)
    xp = client.get("/rank").json()["xp"]
    assert xp["spendable"] == 17 * 40 - 200                # spent recomputed from mulligans

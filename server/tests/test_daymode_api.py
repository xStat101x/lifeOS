"""Day Modes over the API (spec §9): apply/list assignments, day-close honors overrides,
§9.1 anti-exploit (retroactive rejected). Runs against the lifeos-db container.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models import DayEvaluation, DayMode, Habit

DAY = "2026-08-20"       # Thursday, == pinned "today" (free to apply), workout scheduled
DAY_D = date(2026, 8, 20)


def _habit_id(db, name: str) -> str:
    return str(db.query(Habit).filter(Habit.name == name).one().id)


def _mode_id(db, name: str) -> str:
    return str(db.query(DayMode).filter(DayMode.name == name).one().id)


def _log(client, db, name: str, day: str = DAY, **kw) -> None:
    client.post("/logs", json={"target_kind": "habit", "target_id": _habit_id(db, name),
                               "effective_day": day, **kw})


def _eval(db, target_id: str, day: date = DAY_D) -> DayEvaluation:
    db.expire_all()
    return (db.query(DayEvaluation)
            .filter(DayEvaluation.effective_day == day,
                    DayEvaluation.target_id == target_id)
            .one())


def test_apply_and_list_replaces_active_mode(client, db):
    weekend, travel = _mode_id(db, "Weekend"), _mode_id(db, "Travel")
    r = client.post("/day-assignments", json={"effective_day": DAY, "day_mode_id": weekend})
    assert r.status_code == 201
    assert r.json()["mode_name"] == "Weekend"

    # applying another mode to the same day replaces it (one active mode per day)
    client.post("/day-assignments", json={"effective_day": DAY, "day_mode_id": travel})
    listing = client.get("/day-assignments").json()
    assert len(listing) == 1
    assert listing[0]["mode_name"] == "Travel"


def test_retroactive_application_is_rejected(client, db):
    # 2026-08-19 is before the pinned today (2026-08-20) -> mulligan path, not supported yet
    r = client.post("/day-assignments",
                    json={"effective_day": "2026-08-19", "day_mode_id": _mode_id(db, "Weekend")})
    assert r.status_code == 409
    assert "mulligan" in r.json()["detail"].lower()


def test_unknown_mode_404(client, db):
    import uuid
    r = client.post("/day-assignments",
                    json={"effective_day": DAY, "day_mode_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_scored_today_cannot_be_reclassified_for_free(client, db):
    """Invariant: closing a day makes later expectation changes retroactive."""
    _log(client, db, "Protein target", value=96, unit="g")
    protein_id = _habit_id(db, "Protein target")

    before = client.post(f"/day-close/{DAY}").json()
    assert _eval(db, protein_id).completion == pytest.approx(0.6)

    direct = client.post(
        "/day-assignments",
        json={"effective_day": DAY, "day_mode_id": _mode_id(db, "Travel")},
    )
    assert direct.status_code == 409
    assert "mulligan" in direct.json()["detail"].lower()

    # The rejected mechanic must not alter either the evaluation or rank.
    after = client.post(f"/day-close/{DAY}").json()
    assert _eval(db, protein_id).completion == pytest.approx(0.6)
    assert after["domains"] == before["domains"]


def test_travel_pauses_fitness_and_scales_protein(client, db):
    # log 96g protein (= 0.6 * 160) and a workout
    _log(client, db, "Protein target", value=96, unit="g")
    _log(client, db, "Workout")
    protein_id, workout_id = _habit_id(db, "Protein target"), _habit_id(db, "Workout")

    # Planned before close: Travel is free and scales 96/160 to 96/96 = 1.0.
    travel = _mode_id(db, "Travel")
    client.post("/day-assignments", json={"effective_day": DAY, "day_mode_id": travel})
    close = client.post(f"/day-close/{DAY}").json()

    protein_eval = _eval(db, protein_id)
    assert protein_eval.completion == pytest.approx(1.0)          # met the reduced bar
    assert str(protein_eval.applied_mode_id) == travel           # mode recorded on the eval
    assert _eval(db, workout_id).was_paused is True              # Fitness paused
    assert close["domains"]["fitness"]["lp"] == 0.0              # paused => no gain/decay


def test_weekend_neutralizes_wake_timing(client, db):
    # Planned before close: an out-of-window wake has its timing neutralized.
    _log(client, db, "Wake time", meta={"timing_in_window": False})
    wake_id = _habit_id(db, "Wake time")

    client.post("/day-assignments", json={"effective_day": DAY, "day_mode_id": _mode_id(db, "Weekend")})
    client.post(f"/day-close/{DAY}")
    assert _eval(db, wake_id).timing is None                      # timing neutralized (§9.3)


def test_sick_scales_targets_down(client, db):
    # 80g protein = 0.5 * 160; Sick (mild) scales nutrition targets x0.5 -> completion 1.0
    _log(client, db, "Protein target", value=80, unit="g")
    protein_id = _habit_id(db, "Protein target")

    # Planned before close: the reduced expectation can still earn normal credit.
    client.post("/day-assignments", json={"effective_day": DAY, "day_mode_id": _mode_id(db, "Sick")})
    client.post(f"/day-close/{DAY}")
    assert _eval(db, protein_id).completion == pytest.approx(1.0)

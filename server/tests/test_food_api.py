"""Food quick-log API (§6.8, §14): capture, templates, portion-aware re-log, scoring."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models import DayEvaluation, Habit, Log, Meal, MealTemplate

DAY = "2026-08-20"
DAY_D = date(2026, 8, 20)


def _habit_id(db, name: str):
    return db.query(Habit).filter(Habit.name == name).one().id


def _completion(db, habit_name: str) -> float:
    db.expire_all()
    row = (
        db.query(DayEvaluation)
        .filter(
            DayEvaluation.effective_day == DAY_D,
            DayEvaluation.target_id == _habit_id(db, habit_name),
        )
        .one()
    )
    return row.completion


def test_manual_meal_drives_nutrition_completion(client, db):
    meal_id = uuid.uuid4()
    payload = {
        "id": str(meal_id),
        "effective_day": DAY,
        "calories": 2800,
        "protein": 160,
        "description": "Full day quick log",
    }
    logged = client.post("/meals", json=payload)
    assert logged.status_code == 201
    assert logged.json()["id"] == str(meal_id)             # client UUID preserved

    retried = client.post("/meals", json=payload)
    assert retried.status_code == 201
    assert db.query(Meal).count() == 1
    assert db.query(Log).count() == 2                       # no doubled macro logs

    client.post(f"/day-close/{DAY}")
    assert _completion(db, "Calorie target") == pytest.approx(1.0)
    assert _completion(db, "Protein target") == pytest.approx(1.0)

    meal = db.get(Meal, meal_id)
    assert meal is not None and meal.source == "manual" and meal.confirmed is True


def test_multiple_meals_accumulate_toward_daily_targets(client, db):
    for description in ("Meal one", "Meal two"):
        response = client.post(
            "/meals",
            json={
                "effective_day": DAY,
                "calories": 1400,
                "protein": 80,
                "description": description,
            },
        )
        assert response.status_code == 201

    assert db.query(Meal).count() == 2
    assert db.query(Log).count() == 4
    client.post(f"/day-close/{DAY}")
    assert _completion(db, "Calorie target") == pytest.approx(1.0)
    assert _completion(db, "Protein target") == pytest.approx(1.0)


def test_template_round_trips(client, db):
    template_id = uuid.uuid4()
    created = client.post(
        "/meal-templates",
        json={
            "id": str(template_id),
            "name": "Daily shake",
            "calories": 720,
            "protein": 52,
        },
    )
    assert created.status_code == 201
    assert created.json() == {
        "id": str(template_id),
        "name": "Daily shake",
        "calories": 720.0,
        "protein": 52.0,
        "tap_count": 0,
        "last_used": None,
    }

    listed = client.get("/meal-templates")
    assert listed.status_code == 200
    assert listed.json() == [created.json()]


def test_template_relog_scales_macros_by_portion(client, db):
    template = client.post(
        "/meal-templates",
        json={"name": "Rice bowl", "calories": 600, "protein": 40},
    ).json()
    meal_id = uuid.uuid4()

    relog = client.post(
        f"/meal-templates/{template['id']}/relog",
        json={
            "id": str(meal_id),
            "effective_day": DAY,
            "portion_multiplier": 1.5,
        },
    )
    assert relog.status_code == 201
    body = relog.json()
    assert body["id"] == str(meal_id)
    assert body["calories"] == pytest.approx(900.0)
    assert body["protein"] == pytest.approx(60.0)
    assert body["template_id"] == template["id"]

    db.expire_all()
    stored = db.get(Meal, meal_id)
    memory = db.get(MealTemplate, uuid.UUID(template["id"]))
    assert stored.calories == pytest.approx(900.0)
    assert stored.protein == pytest.approx(60.0)
    assert memory.tap_count == 1 and memory.last_used is not None


def test_photo_source_accepts_precomputed_macros_without_an_agent(client, db):
    response = client.post(
        "/meals",
        json={
            "effective_day": DAY,
            "source": "photo",
            "photo_ref": "queued/photo-123.jpg",
            "calories": 850,
            "protein": 48,
            "confidence": 0.82,
        },
    )
    assert response.status_code == 201
    assert response.json()["source"] == "photo"
    assert response.json()["confidence"] == pytest.approx(0.82)

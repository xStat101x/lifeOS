"""Food quick-log API (§6.8, §14); vision inference remains stubbed until Slice 3."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Meal, MealTemplate
from app.nutrition.capture import (
    DEFAULT_MACRO_RESOLVER,
    MacroResolutionError,
    MacroResolver,
)
from app.nutrition.service import NutritionError, persist_meal, persist_template

router = APIRouter()


def get_macro_resolver() -> MacroResolver:
    """Dependency seam: Slice 3 swaps in a vision-backed resolver."""
    return DEFAULT_MACRO_RESOLVER


class MealIn(BaseModel):
    id: uuid.UUID | None = None
    effective_day: date
    calories: float | None = Field(default=None, ge=0)
    protein: float | None = Field(default=None, ge=0)
    description: str | None = None
    source: Literal["manual", "voice", "photo"] = "manual"
    logged_at: datetime | None = None
    photo_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class MealOut(BaseModel):
    id: uuid.UUID
    logged_at: datetime
    effective_day: date
    calories: float
    protein: float
    description: str | None
    source: str
    photo_ref: str | None
    template_id: uuid.UUID | None
    confidence: float | None
    confirmed: bool


class MealTemplateIn(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)


class MealTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    calories: float
    protein: float
    tap_count: int
    last_used: datetime | None


class RelogIn(BaseModel):
    id: uuid.UUID | None = None
    effective_day: date
    portion_multiplier: float = Field(default=1.0, ge=0.5, le=2.0)
    logged_at: datetime | None = None
    description: str | None = None


def _meal_out(row: Meal) -> MealOut:
    return MealOut(
        id=row.id,
        logged_at=row.logged_at,
        effective_day=row.effective_day,
        calories=float(row.calories or 0),
        protein=float(row.protein or 0),
        description=row.description,
        source=row.source,
        photo_ref=row.photo_ref,
        template_id=row.template_id,
        confidence=row.confidence,
        confirmed=row.confirmed,
    )


def _template_out(row: MealTemplate) -> MealTemplateOut:
    return MealTemplateOut(
        id=row.id,
        name=row.name,
        calories=float(row.calories or 0),
        protein=float(row.protein or 0),
        tap_count=row.tap_count,
        last_used=row.last_used,
    )


def _raise_nutrition(error: NutritionError) -> None:
    raise HTTPException(error.status, error.detail)


@router.post("/meals", response_model=MealOut, status_code=201)
def create_meal(
    body: MealIn,
    session: Session = Depends(get_session),
    resolver: MacroResolver = Depends(get_macro_resolver),
) -> MealOut:
    try:
        estimate = resolver.resolve(
            source=body.source,
            calories=body.calories,
            protein=body.protein,
            description=body.description,
            photo_ref=body.photo_ref,
            confidence=body.confidence,
        )
        row, _ = persist_meal(
            session,
            meal_id=body.id,
            logged_at=body.logged_at or datetime.now(timezone.utc),
            effective_day=body.effective_day,
            calories=estimate.calories,
            protein=estimate.protein,
            description=body.description,
            source=body.source,
            photo_ref=body.photo_ref,
            confidence=estimate.confidence,
        )
        session.commit()
        return _meal_out(row)
    except MacroResolutionError as error:
        session.rollback()
        raise HTTPException(422, str(error))
    except NutritionError as error:
        session.rollback()
        _raise_nutrition(error)

@router.post("/meal-templates", response_model=MealTemplateOut, status_code=201)
def create_template(
    body: MealTemplateIn, session: Session = Depends(get_session)
) -> MealTemplateOut:
    try:
        row, _ = persist_template(
            session,
            template_id=body.id,
            name=body.name,
            calories=body.calories,
            protein=body.protein,
        )
        session.commit()
        return _template_out(row)
    except NutritionError as error:
        session.rollback()
        _raise_nutrition(error)


@router.get("/meal-templates", response_model=list[MealTemplateOut])
def list_templates(session: Session = Depends(get_session)) -> list[MealTemplateOut]:
    rows = (
        session.query(MealTemplate)
        .filter(MealTemplate.deleted_at.is_(None))
        .order_by(MealTemplate.name, MealTemplate.id)
        .all()
    )
    return [_template_out(row) for row in rows]


@router.post(
    "/meal-templates/{template_id}/relog", response_model=MealOut, status_code=201
)
def relog_template(
    template_id: uuid.UUID,
    body: RelogIn,
    session: Session = Depends(get_session),
) -> MealOut:
    template = session.get(MealTemplate, template_id)
    if template is None or template.deleted_at is not None:
        raise HTTPException(404, "meal_template not found")
    if template.calories is None or template.protein is None:
        raise HTTPException(422, "meal_template must have calories and protein")

    logged_at = body.logged_at or datetime.now(timezone.utc)
    try:
        row, created = persist_meal(
            session,
            meal_id=body.id,
            logged_at=logged_at,
            effective_day=body.effective_day,
            calories=template.calories * body.portion_multiplier,
            protein=template.protein * body.portion_multiplier,
            description=body.description or template.name,
            source="template",
            template_id=template.id,
            portion_multiplier=body.portion_multiplier,
        )
        if created:
            template.tap_count += 1
            template.last_used = logged_at
        session.commit()
        return _meal_out(row)
    except NutritionError as error:
        session.rollback()
        _raise_nutrition(error)

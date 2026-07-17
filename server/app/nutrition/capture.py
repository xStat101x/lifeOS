"""Macro-resolution boundary for manual/voice/photo meal capture.

Slice 1 accepts user- or client-computed macros for every source. Slice 3 can replace
``PrecomputedMacroResolver`` with a vision-backed implementation of ``MacroResolver``
without changing the HTTP request or meal persistence shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MacroResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class MacroEstimate:
    calories: float
    protein: float
    confidence: float | None = None


class MacroResolver(Protocol):
    def resolve(
        self,
        *,
        source: str,
        calories: float | None,
        protein: float | None,
        description: str | None,
        photo_ref: str | None,
        confidence: float | None,
    ) -> MacroEstimate: ...


class PrecomputedMacroResolver:
    """Current photo stub: accept macros computed elsewhere; never calls a model."""

    def resolve(
        self,
        *,
        source: str,
        calories: float | None,
        protein: float | None,
        description: str | None,
        photo_ref: str | None,
        confidence: float | None,
    ) -> MacroEstimate:
        if calories is None or protein is None:
            if source == "photo":
                raise MacroResolutionError(
                    "Photo vision is stubbed until Slice 3; provide pre-computed calories "
                    "and protein with source='photo'."
                )
            raise MacroResolutionError("calories and protein are required")
        if calories < 0 or protein < 0:
            raise MacroResolutionError("calories and protein must be non-negative")
        return MacroEstimate(
            calories=float(calories), protein=float(protein), confidence=confidence
        )


DEFAULT_MACRO_RESOLVER = PrecomputedMacroResolver()

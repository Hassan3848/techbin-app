"""
Waste label and recyclability mapping utilities for TechBin.

This module is intentionally small and strict because the ML output must be
converted into trusted product logic before analytics are updated.

Supported waste classes:
    cardboard, glass, metal, paper, plastic, trash

Category mapping:
    cardboard, glass, metal, paper, plastic -> recyclable
    trash -> non-recyclable
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.config import (
    NON_RECYCLABLE,
    NON_RECYCLABLE_CLASSES,
    RECYCLABLE,
    RECYCLABLE_CLASSES,
    WASTE_CLASSES,
)


class WasteLabelError(ValueError):
    """Raised when a waste label is invalid or unsupported."""


@dataclass(frozen=True)
class LabelMappingResult:
    """
    Normalized label mapping result.

    Attributes:
        original_class: Raw class value received from caller/model.
        normalized_class: Clean class name used by TechBin.
        recyclability: recyclable or non-recyclable.
    """

    original_class: str
    normalized_class: str
    recyclability: str


VALID_WASTE_CLASSES: Final[tuple[str, ...]] = WASTE_CLASSES

WASTE_CLASS_TO_RECYCLABILITY: Final[dict[str, str]] = {
    **{class_name: RECYCLABLE for class_name in RECYCLABLE_CLASSES},
    **{class_name: NON_RECYCLABLE for class_name in NON_RECYCLABLE_CLASSES},
}

# Backward-friendly aliases for older scripts/tests.
LABELS: Final[tuple[str, ...]] = VALID_WASTE_CLASSES
CLASS_NAMES: Final[tuple[str, ...]] = VALID_WASTE_CLASSES


def normalize_waste_class(value: str) -> str:
    """
    Normalize raw waste class text.

    Examples:
        " Plastic " -> "plastic"
        "TRASH" -> "trash"
        "card board" -> "cardboard"
    """

    if not isinstance(value, str):
        raise WasteLabelError(
            f"Waste class must be a string, got {type(value).__name__}"
        )

    normalized = value.strip().lower()
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = " ".join(normalized.split())

    known_aliases = {
        "card board": "cardboard",
        "cardboard waste": "cardboard",
        "glass waste": "glass",
        "metal waste": "metal",
        "paper waste": "paper",
        "plastic waste": "plastic",
        "garbage": "trash",
        "general waste": "trash",
        "non recyclable": "trash",
        "non-recyclable": "trash",
        "non_recyclable": "trash",
    }

    normalized = known_aliases.get(normalized, normalized)

    if normalized not in VALID_WASTE_CLASSES:
        raise WasteLabelError(
            f"Unsupported waste class '{value}'. "
            f"Allowed classes: {', '.join(VALID_WASTE_CLASSES)}"
        )

    return normalized


def is_valid_waste_class(value: str) -> bool:
    """
    Return True if value is a supported TechBin waste class.
    """

    try:
        normalize_waste_class(value)
        return True
    except WasteLabelError:
        return False


def get_recyclability(waste_class: str) -> str:
    """
    Return recyclability category for a waste class.

    Returns:
        recyclable or non-recyclable.
    """

    normalized_class = normalize_waste_class(waste_class)

    try:
        return WASTE_CLASS_TO_RECYCLABILITY[normalized_class]
    except KeyError as exc:
        raise WasteLabelError(
            f"No recyclability mapping found for '{normalized_class}'"
        ) from exc


def is_recyclable(waste_class: str) -> bool:
    """
    Return True if waste class belongs to recyclable category.
    """

    return get_recyclability(waste_class) == RECYCLABLE


def is_non_recyclable(waste_class: str) -> bool:
    """
    Return True if waste class belongs to non-recyclable category.
    """

    return get_recyclability(waste_class) == NON_RECYCLABLE


def map_label(waste_class: str) -> LabelMappingResult:
    """
    Normalize a waste class and return its category mapping.
    """

    normalized_class = normalize_waste_class(waste_class)

    return LabelMappingResult(
        original_class=waste_class,
        normalized_class=normalized_class,
        recyclability=get_recyclability(normalized_class),
    )


def require_valid_waste_class(waste_class: str) -> str:
    """
    Validate and return normalized waste class.

    This helper is useful in modules that need strict input validation.
    """

    return normalize_waste_class(waste_class)


# Compatibility aliases for older prototype code.
normalize_class_name = normalize_waste_class
validate_waste_class = require_valid_waste_class
map_class_to_recyclability = get_recyclability
get_category = get_recyclability


__all__ = [
    "WasteLabelError",
    "LabelMappingResult",
    "VALID_WASTE_CLASSES",
    "WASTE_CLASS_TO_RECYCLABILITY",
    "LABELS",
    "CLASS_NAMES",
    "normalize_waste_class",
    "normalize_class_name",
    "is_valid_waste_class",
    "require_valid_waste_class",
    "validate_waste_class",
    "get_recyclability",
    "get_category",
    "map_class_to_recyclability",
    "is_recyclable",
    "is_non_recyclable",
    "map_label",
]

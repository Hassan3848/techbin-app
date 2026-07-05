"""
Disposal validation engine for TechBin.

This module decides:

1. predicted waste class
2. recyclability category
3. expected bin side
4. actual disposal side
5. correct/incorrect disposal
6. whether the event should be accepted for analytics

Core fixed product rule:
    right side = recyclable
    left side = non-recyclable
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

from app.config import (
    CATEGORY_TO_EXPECTED_SIDE,
    LEFT_SIDE,
    MIN_CONFIDENCE,
    NON_RECYCLABLE,
    RECYCLABLE,
    RIGHT_SIDE,
)
from app.ml.labels import get_recyclability, normalize_waste_class


class DisposalValidationError(ValueError):
    """Raised when disposal validation input is invalid."""


VALID_DISPOSAL_SIDES: Final[tuple[str, ...]] = (
    LEFT_SIDE,
    RIGHT_SIDE,
)


@dataclass(frozen=True)
class DisposalValidationResult:
    """
    Final disposal validation result.

    Attributes:
        predicted_class:
            Normalized waste class from ML/manual input.

        recyclability:
            recyclable or non-recyclable.

        confidence:
            ML confidence score from 0.0 to 1.0.

        disposal_side:
            Actual side used by the user.

        expected_side:
            Correct side according to recyclability rule.

        is_correct_disposal:
            True if actual side equals expected side.

        is_confidence_accepted:
            True if confidence is equal to or above threshold.

        is_event_accepted:
            True only when confidence passed and input was valid.

        rejection_reason:
            None if accepted, otherwise explains why analytics must not count it.
    """

    predicted_class: str
    recyclability: str
    confidence: float
    disposal_side: str
    expected_side: str
    is_correct_disposal: bool
    is_confidence_accepted: bool
    is_event_accepted: bool
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """
        Convert validation result to a plain dictionary.
        """

        return asdict(self)


def normalize_disposal_side(value: str) -> str:
    """
    Normalize disposal side text.

    Accepted examples:
        "right" -> "right"
        "r" -> "right"
        "recyclable" -> "right"

        "left" -> "left"
        "l" -> "left"
        "non-recyclable" -> "left"
    """

    if not isinstance(value, str):
        raise DisposalValidationError(
            f"Disposal side must be a string, got {type(value).__name__}"
        )

    normalized = value.strip().lower()
    normalized = normalized.replace("_", "-")
    normalized = " ".join(normalized.split())

    aliases = {
        "r": RIGHT_SIDE,
        "right": RIGHT_SIDE,
        "right side": RIGHT_SIDE,
        "recyclable": RIGHT_SIDE,
        "recycle": RIGHT_SIDE,
        "recycling": RIGHT_SIDE,

        "l": LEFT_SIDE,
        "left": LEFT_SIDE,
        "left side": LEFT_SIDE,
        "non-recyclable": LEFT_SIDE,
        "non recyclable": LEFT_SIDE,
        "nonrecyclable": LEFT_SIDE,
        "trash": LEFT_SIDE,
        "general waste": LEFT_SIDE,
    }

    side = aliases.get(normalized)

    if side not in VALID_DISPOSAL_SIDES:
        raise DisposalValidationError(
            f"Unsupported disposal side '{value}'. "
            f"Allowed sides: {', '.join(VALID_DISPOSAL_SIDES)}"
        )

    return side


def validate_confidence(confidence: float) -> float:
    """
    Validate and normalize confidence score.

    Confidence must be numeric and between 0.0 and 1.0.
    """

    if isinstance(confidence, bool):
        raise DisposalValidationError("Confidence must be a number, not boolean")

    try:
        normalized_confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise DisposalValidationError(
            f"Confidence must be numeric, got {confidence!r}"
        ) from exc

    if normalized_confidence < 0.0 or normalized_confidence > 1.0:
        raise DisposalValidationError(
            f"Confidence must be between 0.0 and 1.0, got {normalized_confidence}"
        )

    return normalized_confidence


def get_expected_side_for_recyclability(recyclability: str) -> str:
    """
    Return expected disposal side for a recyclability category.
    """

    if not isinstance(recyclability, str):
        raise DisposalValidationError(
            f"Recyclability must be a string, got {type(recyclability).__name__}"
        )

    normalized = recyclability.strip().lower()

    if normalized not in (RECYCLABLE, NON_RECYCLABLE):
        raise DisposalValidationError(
            f"Unsupported recyclability '{recyclability}'. "
            f"Allowed values: {RECYCLABLE}, {NON_RECYCLABLE}"
        )

    try:
        return CATEGORY_TO_EXPECTED_SIDE[normalized]
    except KeyError as exc:
        raise DisposalValidationError(
            f"No expected-side rule found for '{normalized}'"
        ) from exc


def get_expected_side_for_class(waste_class: str) -> str:
    """
    Return expected disposal side for a waste class.
    """

    normalized_class = normalize_waste_class(waste_class)
    recyclability = get_recyclability(normalized_class)
    return get_expected_side_for_recyclability(recyclability)


def is_correct_side(waste_class: str, disposal_side: str) -> bool:
    """
    Return True if the used side matches the expected side for the class.
    """

    expected_side = get_expected_side_for_class(waste_class)
    actual_side = normalize_disposal_side(disposal_side)

    return actual_side == expected_side


def validate_disposal(
    predicted_class: str,
    confidence: float,
    disposal_side: str,
    min_confidence: float = MIN_CONFIDENCE,
) -> DisposalValidationResult:
    """
    Validate a complete disposal decision.

    This function does not decide whether a camera capture happened.
    It only validates the business logic after class + side are known.

    Event acceptance rule:
        event is accepted only when confidence >= min_confidence.

    Correctness rule:
        correct disposal means actual side == expected side.
    """

    normalized_class = normalize_waste_class(predicted_class)
    normalized_confidence = validate_confidence(confidence)
    normalized_side = normalize_disposal_side(disposal_side)

    normalized_min_confidence = validate_confidence(min_confidence)

    recyclability = get_recyclability(normalized_class)
    expected_side = get_expected_side_for_recyclability(recyclability)

    is_correct = normalized_side == expected_side
    is_confidence_accepted = normalized_confidence >= normalized_min_confidence

    rejection_reason = None
    if not is_confidence_accepted:
        rejection_reason = (
            f"low_confidence: {normalized_confidence:.3f} "
            f"< {normalized_min_confidence:.3f}"
        )

    return DisposalValidationResult(
        predicted_class=normalized_class,
        recyclability=recyclability,
        confidence=normalized_confidence,
        disposal_side=normalized_side,
        expected_side=expected_side,
        is_correct_disposal=is_correct,
        is_confidence_accepted=is_confidence_accepted,
        is_event_accepted=is_confidence_accepted,
        rejection_reason=rejection_reason,
    )


# Compatibility-friendly aliases for older/alternate naming.
validate_disposal_event = validate_disposal
expected_side_for_class = get_expected_side_for_class
expected_side_for_recyclability = get_expected_side_for_recyclability


__all__ = [
    "DisposalValidationError",
    "DisposalValidationResult",
    "VALID_DISPOSAL_SIDES",
    "normalize_disposal_side",
    "validate_confidence",
    "get_expected_side_for_recyclability",
    "get_expected_side_for_class",
    "expected_side_for_recyclability",
    "expected_side_for_class",
    "is_correct_side",
    "validate_disposal",
    "validate_disposal_event",
]

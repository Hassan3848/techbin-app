"""
Test TechBin label mapping and disposal validator.

Run from project root:
    PYTHONPATH=. python3 tests/test_labels_validator.py
"""

from __future__ import annotations

from pprint import pprint

from app.config import LEFT_SIDE, NON_RECYCLABLE, RECYCLABLE, RIGHT_SIDE
from app.engine.disposal_validator import (
    DisposalValidationError,
    get_expected_side_for_class,
    normalize_disposal_side,
    validate_disposal,
)
from app.ml.labels import (
    VALID_WASTE_CLASSES,
    WasteLabelError,
    get_recyclability,
    is_recyclable,
    normalize_waste_class,
)


def test_label_mapping() -> None:
    expected = {
        "cardboard": RECYCLABLE,
        "glass": RECYCLABLE,
        "metal": RECYCLABLE,
        "paper": RECYCLABLE,
        "plastic": RECYCLABLE,
        "trash": NON_RECYCLABLE,
    }

    print()
    print("========== Label Mapping ==========")

    for waste_class, expected_category in expected.items():
        category = get_recyclability(waste_class)

        print(waste_class, "=>", category)

        assert category == expected_category

    assert normalize_waste_class(" Plastic ") == "plastic"
    assert normalize_waste_class("card board") == "cardboard"
    assert is_recyclable("plastic") is True
    assert is_recyclable("trash") is False

    try:
        normalize_waste_class("banana")
        raise AssertionError("banana should not be accepted as a direct model class")
    except WasteLabelError:
        pass

    print("PASS: label mapping")


def test_expected_sides() -> None:
    print()
    print("========== Expected Side Rules ==========")

    recyclable_classes = ("cardboard", "glass", "metal", "paper", "plastic")

    for waste_class in recyclable_classes:
        expected_side = get_expected_side_for_class(waste_class)
        print(waste_class, "=>", expected_side)
        assert expected_side == RIGHT_SIDE

    expected_side = get_expected_side_for_class("trash")
    print("trash =>", expected_side)
    assert expected_side == LEFT_SIDE

    print("PASS: expected side rules")


def test_disposal_side_normalization() -> None:
    print()
    print("========== Side Normalization ==========")

    assert normalize_disposal_side("right") == RIGHT_SIDE
    assert normalize_disposal_side("r") == RIGHT_SIDE
    assert normalize_disposal_side("recyclable") == RIGHT_SIDE

    assert normalize_disposal_side("left") == LEFT_SIDE
    assert normalize_disposal_side("l") == LEFT_SIDE
    assert normalize_disposal_side("non-recyclable") == LEFT_SIDE

    try:
        normalize_disposal_side("middle")
        raise AssertionError("middle should not be accepted as a side")
    except DisposalValidationError:
        pass

    print("PASS: side normalization")


def test_disposal_validation_cases() -> None:
    cases = [
        {
            "case": "plastic_right_correct",
            "predicted_class": "plastic",
            "confidence": 0.91,
            "disposal_side": "right",
            "expected_side": "right",
            "expected_correct": True,
            "expected_accepted": True,
        },
        {
            "case": "plastic_left_incorrect",
            "predicted_class": "plastic",
            "confidence": 0.91,
            "disposal_side": "left",
            "expected_side": "right",
            "expected_correct": False,
            "expected_accepted": True,
        },
        {
            "case": "trash_left_correct",
            "predicted_class": "trash",
            "confidence": 0.88,
            "disposal_side": "left",
            "expected_side": "left",
            "expected_correct": True,
            "expected_accepted": True,
        },
        {
            "case": "trash_right_incorrect",
            "predicted_class": "trash",
            "confidence": 0.88,
            "disposal_side": "right",
            "expected_side": "left",
            "expected_correct": False,
            "expected_accepted": True,
        },
        {
            "case": "metal_low_confidence_rejected",
            "predicted_class": "metal",
            "confidence": 0.40,
            "disposal_side": "right",
            "expected_side": "right",
            "expected_correct": True,
            "expected_accepted": False,
        },
    ]

    print()
    print("========== Disposal Validation ==========")

    for case in cases:
        result = validate_disposal(
            predicted_class=case["predicted_class"],
            confidence=case["confidence"],
            disposal_side=case["disposal_side"],
        )

        print()
        print("Case:", case["case"])
        pprint(result.to_dict())

        assert result.predicted_class == case["predicted_class"]
        assert result.expected_side == case["expected_side"]
        assert result.is_correct_disposal is case["expected_correct"]
        assert result.is_event_accepted is case["expected_accepted"]

    print("PASS: disposal validation cases")


def main() -> None:
    print("Valid waste classes:", VALID_WASTE_CLASSES)

    test_label_mapping()
    test_expected_sides()
    test_disposal_side_normalization()
    test_disposal_validation_cases()

    print()
    print("All labels/validator tests passed.")


if __name__ == "__main__":
    main()

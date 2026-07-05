"""
Test TechBin capacity indicator module without touching GPIO.

Run:
    PYTHONPATH=. python3 tests/test_capacity_indicator.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.capacity_indicator import (
    CapacityIndicator,
    CapacityIndicatorConfig,
    SimulatedCapacityIndicatorBackend,
    build_dual_capacity_indicators,
)
from app.sensors.fill_level import FillLevelConfig, estimate_fill_level_from_distance
from app.sensors.pin_map import PIN_MAP, validate_pin_map


def test_disabled_indicator() -> None:
    print()
    print("========== Disabled Indicator ==========")

    backend = SimulatedCapacityIndicatorBackend()

    indicator = CapacityIndicator(
        config=CapacityIndicatorConfig(
            name="test_indicator",
            red_gpio=17,
            yellow_gpio=27,
            green_gpio=22,
            role="test_capacity",
            enabled=False,
        ),
        backend=backend,
    )

    state = indicator.set_color("green")

    pprint(state.to_dict())

    assert state.valid is False
    assert state.activeColor == "off"
    assert state.faultCode == "capacity_indicator_not_enabled"

    print("PASS: disabled indicator")


def test_single_indicator_colors() -> None:
    print()
    print("========== Single Indicator Colors ==========")

    backend = SimulatedCapacityIndicatorBackend()

    indicator = CapacityIndicator(
        config=CapacityIndicatorConfig(
            name="test_indicator",
            red_gpio=17,
            yellow_gpio=27,
            green_gpio=22,
            role="test_capacity",
            enabled=True,
        ),
        backend=backend,
    )

    for color in ("green", "yellow", "red", "off"):
        state = indicator.set_color(color)
        raw_state = backend.get_state("test_indicator")

        print(color, "=>")
        pprint(state.to_dict())
        pprint(raw_state)

        assert state.valid is True
        assert state.activeColor == color

        if color == "green":
            assert raw_state == {"red": False, "yellow": False, "green": True}
        elif color == "yellow":
            assert raw_state == {"red": False, "yellow": True, "green": False}
        elif color == "red":
            assert raw_state == {"red": True, "yellow": False, "green": False}
        elif color == "off":
            assert raw_state == {"red": False, "yellow": False, "green": False}

    print("PASS: single indicator colors")


def test_apply_fill_level_to_indicator() -> None:
    print()
    print("========== Apply Fill Level ==========")

    backend = SimulatedCapacityIndicatorBackend()

    indicator = CapacityIndicator(
        config=CapacityIndicatorConfig(
            name="left_capacity_indicator",
            red_gpio=17,
            yellow_gpio=27,
            green_gpio=22,
            role="left_compartment_capacity",
            enabled=True,
        ),
        backend=backend,
    )

    fill_config = FillLevelConfig(
        compartment_name="left_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    low_fill = estimate_fill_level_from_distance(40.0, fill_config)
    half_fill = estimate_fill_level_from_distance(25.0, fill_config)
    full_fill = estimate_fill_level_from_distance(8.0, fill_config)

    low_state = indicator.apply_fill_level(low_fill)
    assert low_state.activeColor == "green"

    half_state = indicator.apply_fill_level(half_fill)
    assert half_state.activeColor == "yellow"

    full_state = indicator.apply_fill_level(full_fill)
    assert full_state.activeColor == "red"

    pprint(low_state.to_dict())
    pprint(half_state.to_dict())
    pprint(full_state.to_dict())

    print("PASS: apply fill level")


def test_dual_indicators_from_pin_map() -> None:
    print()
    print("========== Dual Indicators From Pin Map ==========")

    validate_pin_map()

    backend = SimulatedCapacityIndicatorBackend()

    indicators = build_dual_capacity_indicators(
        left_pin_config=PIN_MAP.traffic_light_left,
        right_pin_config=PIN_MAP.traffic_light_right,
        enabled=True,
        backend=backend,
    )

    left_config = FillLevelConfig(
        compartment_name="left_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
    )

    right_config = FillLevelConfig(
        compartment_name="right_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
    )

    left_fill = estimate_fill_level_from_distance(40.0, left_config)   # green
    right_fill = estimate_fill_level_from_distance(8.0, right_config)  # red

    states = indicators.apply(
        left_fill=left_fill,
        right_fill=right_fill,
    )

    pprint(states)

    assert states["left"]["activeColor"] == "green"
    assert states["right"]["activeColor"] == "red"

    print("PASS: dual indicators")


def main() -> None:
    test_disabled_indicator()
    test_single_indicator_colors()
    test_apply_fill_level_to_indicator()
    test_dual_indicators_from_pin_map()

    print()
    print("All capacity indicator tests passed.")


if __name__ == "__main__":
    main()

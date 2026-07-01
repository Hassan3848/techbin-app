#!/usr/bin/env python3
"""
Test TechBin's real direct-Pi side detector.

Usage:
    PYTHONPATH="$PWD" python3 scripts/test_real_app_side_detection.py left
    PYTHONPATH="$PWD" python3 scripts/test_real_app_side_detection.py right
"""

from __future__ import annotations

import argparse

from app.sensors.direct_pi_stack import build_direct_pi_hardware_stack


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "expected_side",
        choices=("left", "right"),
        help="Compartment where you will place the test object.",
    )
    args = parser.parse_args()

    stack = build_direct_pi_hardware_stack()

    try:
        print()
        print("=== TechBin Real App Side-Detection Test ===")
        print(f"Expected side: {args.expected_side.upper()}")
        print()
        input(
            "Remove every object from BOTH compartments, stand back, "
            "then press Enter to capture baseline..."
        )

        left_base, right_base = stack.side_detector.capture_baseline()

        print()
        print(f"Baseline left : {left_base.distanceCm} cm")
        print(f"Baseline right: {right_base.distanceCm} cm")
        print()

        input(
            f"Place or hold a book/cardboard 10–20 cm below the "
            f"{args.expected_side.upper()} sensor, keep it still, "
            "then press Enter..."
        )

        result = stack.side_detector.detect_once()
        data = result.to_dict()

        left = data["leftEvidence"]
        right = data["rightEvidence"]

        print()
        print("=== Result ===")
        print(
            f"LEFT  | baseline={left['baselineDistanceCm']} cm | "
            f"current={left['currentDistanceCm']} cm | "
            f"delta={left['deltaCm']} cm"
        )
        print(
            f"RIGHT | baseline={right['baselineDistanceCm']} cm | "
            f"current={right['currentDistanceCm']} cm | "
            f"delta={right['deltaCm']} cm"
        )
        print()
        print(f"Detected side: {data['detectedSide'].upper()}")
        print(f"Expected side: {args.expected_side.upper()}")
        print(f"Valid        : {data['valid']}")
        print(f"Message      : {data['message']}")

        if data["detectedSide"] == args.expected_side and data["valid"]:
            print("\nRESULT: PASS — real application side detection works.")
        else:
            print("\nRESULT: Review readings and repeat with a clearer object position.")

    finally:
        stack.close()
        print("\nGPIO resources released; traffic lights are OFF.")


if __name__ == "__main__":
    main()

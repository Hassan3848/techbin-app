#!/usr/bin/env python3
"""
TechBin left traffic-light hardware test.
Tests red, yellow, green, then turns everything off.
"""

from __future__ import annotations

import time

from gpiozero import LED


LIGHTS = {
    "RED": LED(17, active_high=True, initial_value=False),
    "YELLOW": LED(27, active_high=True, initial_value=False),
    "GREEN": LED(22, active_high=True, initial_value=False),
}


def all_off() -> None:
    for light in LIGHTS.values():
        light.off()


try:
    all_off()
    print("Starting LEFT traffic-light test.")

    for colour in ("RED", "YELLOW", "GREEN"):
        all_off()
        print(f"{colour} should be ON for 3 seconds.")
        LIGHTS[colour].on()
        time.sleep(3)

        LIGHTS[colour].off()
        print("All lights should be OFF for 1 second.")
        time.sleep(1)

    print("Test complete. All left traffic-light LEDs are OFF.")

finally:
    all_off()

    for light in LIGHTS.values():
        light.close()

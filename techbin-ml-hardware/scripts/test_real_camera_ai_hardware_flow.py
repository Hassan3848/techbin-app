#!/usr/bin/env python3
"""
One real TechBin camera + AI + sensor disposal test.

This is a standalone test script.
It does not change main_runtime.py and does not write dashboard analytics.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from picamera2 import Picamera2

from app.sensors.direct_pi_stack import build_direct_pi_hardware_stack


PROJECT_DIR = Path(__file__).resolve().parents[1]

MODEL_PACKAGE = Path(
    "/home/hassan/TechBin/model_tests/techbin_effnetv2_pi_test_package"
)
MODEL_PATH = MODEL_PACKAGE / "techbin_effnetv2_camera_dynamic_range.tflite"
LABELS_PATH = MODEL_PACKAGE / "labels.json"
CONFIG_PATH = MODEL_PACKAGE / "preprocessing_config.json"

CAPTURE_DIR = PROJECT_DIR / "captures" / "integrated_test"

RECYCLABLE = {"cardboard", "paper", "plastic_glass"}
NON_RECYCLABLE = {"trash"}

FRONT_POLL_SECONDS = 0.45
CAMERA_WARMUP_SECONDS = 1.5
ITEM_POSITION_SECONDS = 2.5

AVERAGE_FRAMES = 5
FRAME_INTERVAL_SECONDS = 0.20

MIN_CONFIDENCE = 0.60
MIN_MARGIN = 0.12

SIDE_CONFIRM_TIMEOUT_SECONDS = 12.0
SIDE_POLL_SECONDS = 0.45


def load_interpreter(model_path: Path):
    try:
        from ai_edge_litert.interpreter import Interpreter
        return Interpreter(model_path=str(model_path)), "ai_edge_litert"
    except Exception:
        pass

    try:
        from tflite_runtime.interpreter import Interpreter
        return Interpreter(model_path=str(model_path)), "tflite_runtime"
    except Exception:
        pass

    try:
        import tensorflow as tf
        return tf.lite.Interpreter(model_path=str(model_path)), "tensorflow.lite"
    except Exception as exc:
        raise RuntimeError(
            "No LiteRT/TFLite interpreter is available in this environment."
        ) from exc


def load_labels(path: Path) -> dict[int, str]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return {index: str(label) for index, label in enumerate(data)}

    if isinstance(data, dict):
        return {int(index): str(label) for index, label in data.items()}

    raise ValueError("labels.json must contain a list or dictionary.")


def softmax_if_needed(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)

    total = float(np.sum(values))
    if np.min(values) < -0.01 or np.max(values) > 1.2 or abs(total - 1.0) > 0.25:
        values = values - np.max(values)
        exponentials = np.exp(values)
        values = exponentials / np.sum(exponentials)

    return values


def preprocess(frame_rgb: np.ndarray, image_size: list[int], input_dtype) -> np.ndarray:
    image = Image.fromarray(frame_rgb).convert("RGB")
    image = image.resize((image_size[0], image_size[1]), Image.BILINEAR)

    array = np.asarray(image, dtype=np.float32)

    # EfficientNetV2 has preprocessing inside the model.
    # Feed RGB float32 values in the range 0..255.
    if input_dtype == np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    else:
        array = array.astype(input_dtype)

    return array[None, ...]


def predict_probs(
    interpreter,
    input_details: list[dict],
    output_details: list[dict],
    frame_rgb: np.ndarray,
    image_size: list[int],
) -> np.ndarray:
    input_tensor = preprocess(
        frame_rgb=frame_rgb,
        image_size=image_size,
        input_dtype=input_details[0]["dtype"],
    )

    interpreter.set_tensor(input_details[0]["index"], input_tensor)
    interpreter.invoke()

    output = interpreter.get_tensor(output_details[0]["index"])[0]

    scale, zero_point = output_details[0].get("quantization", (0.0, 0))
    if scale and scale > 0:
        output = scale * (output.astype(np.float32) - zero_point)

    return softmax_if_needed(output)


def capture_corrected_rgb_frame(camera: Picamera2) -> np.ndarray:
    frame = camera.capture_array()

    if frame.ndim != 3 or frame.shape[2] < 3:
        raise RuntimeError(f"Unexpected camera frame shape: {frame.shape}")

    frame = frame[:, :, :3]

    # Required Pi Camera RB correction from your tested model setup.
    return frame[:, :, [2, 1, 0]]


def capture_average_prediction(
    camera: Picamera2,
    interpreter,
    input_details: list[dict],
    output_details: list[dict],
    image_size: list[int],
) -> tuple[np.ndarray, Path]:
    probabilities: list[np.ndarray] = []
    saved_frame: np.ndarray | None = None

    for frame_number in range(AVERAGE_FRAMES):
        frame_rgb = capture_corrected_rgb_frame(camera)

        if saved_frame is None:
            saved_frame = frame_rgb.copy()

        probabilities.append(
            predict_probs(
                interpreter=interpreter,
                input_details=input_details,
                output_details=output_details,
                frame_rgb=frame_rgb,
                image_size=image_size,
            )
        )

        if frame_number < AVERAGE_FRAMES - 1:
            time.sleep(FRAME_INTERVAL_SECONDS)

    if saved_frame is None:
        raise RuntimeError("No camera frame was captured.")

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    capture_path = CAPTURE_DIR / (
        f"integrated_test_{datetime.now():%Y%m%d_%H%M%S_%f}.jpg"
    )
    Image.fromarray(saved_frame).save(capture_path, quality=95)

    average_probs = np.mean(np.stack(probabilities), axis=0)
    return average_probs, capture_path


def print_capacity(label: str, data: dict) -> None:
    fill = data.get("fillLevel", {})
    indicator = data.get("indicatorState", {})

    print(
        f"{label:5} | "
        f"distance={fill.get('distanceCm')} cm | "
        f"fill={fill.get('fillPercentage')}% | "
        f"light={indicator.get('activeColor')}"
    )


def main() -> None:
    for required_path in (MODEL_PATH, LABELS_PATH, CONFIG_PATH):
        if not required_path.exists():
            raise FileNotFoundError(f"Required model file not found: {required_path}")

    labels = load_labels(LABELS_PATH)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    image_size = config.get("image_size", [224, 224])
    if isinstance(image_size, int):
        image_size = [image_size, image_size]

    interpreter, backend = load_interpreter(MODEL_PATH)
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    stack = None
    camera = None

    try:
        print()
        print("=== TechBin Real Camera + AI + Hardware Test ===")
        print(f"Model: {MODEL_PATH.name}")
        print(f"Backend: {backend}")
        print(f"Labels: {labels}")
        print(f"Model input: {input_details[0]['shape']} / {input_details[0]['dtype']}")
        print()
        print("Test instructions:")
        print("1. Keep both compartments clear before starting.")
        print("2. Stand away from the front sensor.")
        print("3. Move within about 20–25 cm to start a session.")
        print("4. When prompted, hold one item clearly in the camera view.")
        print("5. Do NOT place it in either compartment until instructed.")
        print("6. Place it in the suggested compartment.")
        print("7. Keep it under that compartment sensor.")
        print("Press Ctrl+C to stop safely.")
        print()

        stack = build_direct_pi_hardware_stack()

        camera = Picamera2()
        camera_config = camera.create_preview_configuration(
            main={"size": (720, 720), "format": "RGB888"}
        )
        camera.configure(camera_config)
        camera.start()
        time.sleep(CAMERA_WARMUP_SECONDS)

        print("Camera started. Waiting for front session...")

        while True:
            session_data = stack.session_detector.update().to_dict()

            distance = (session_data.get("ultrasonicReading") or {}).get("distanceCm")
            active = session_data.get("sessionActive")
            started = session_data.get(
                "sessionStarted",
                session_data.get("started", False),
            )

            print(
                f"FRONT | distance={distance} cm | "
                f"active={active} | started={started}"
            )

            if started:
                break

            time.sleep(FRONT_POLL_SECONDS)

        print("\nFront session started.")
        print("Capturing left/right compartment baseline...")

        left_baseline, right_baseline = stack.side_detector.capture_baseline()

        print(f"Baseline LEFT : {left_baseline.distanceCm} cm")
        print(f"Baseline RIGHT: {right_baseline.distanceCm} cm")

        print()
        print(
            f"Position the item clearly in front of the camera now. "
            f"Capturing in {ITEM_POSITION_SECONDS:.1f} seconds..."
        )
        time.sleep(ITEM_POSITION_SECONDS)

        average_probs, capture_path = capture_average_prediction(
            camera=camera,
            interpreter=interpreter,
            input_details=input_details,
            output_details=output_details,
            image_size=image_size,
        )

        sorted_indexes = np.argsort(average_probs)[::-1]
        top3 = [
            (
                labels.get(int(index), f"class_{int(index)}"),
                float(average_probs[int(index)]),
            )
            for index in sorted_indexes[:3]
        ]

        predicted_class, confidence = top3[0]
        margin = top3[0][1] - top3[1][1] if len(top3) > 1 else confidence

        print()
        print("=== CAMERA / AI RESULT ===")
        print(f"Captured image: {capture_path}")
        print(f"Prediction: {predicted_class}")
        print(f"Confidence: {confidence * 100:.1f}%")
        print(f"Top-2 margin: {margin * 100:.1f}%")
        print(
            "Top-3: "
            + " | ".join(f"{label} {score * 100:.1f}%" for label, score in top3)
        )

        if confidence < MIN_CONFIDENCE or margin < MIN_MARGIN:
            print()
            print("RESULT: UNCERTAIN CAMERA PREDICTION")
            print("No compartment is suggested and no disposal is counted.")
            print(
                f"Required: confidence >= {MIN_CONFIDENCE * 100:.0f}% and "
                f"margin >= {MIN_MARGIN * 100:.0f}%"
            )
            return

        if predicted_class in RECYCLABLE:
            expected_side = "right"
            waste_group = "RECYCLABLE"
        elif predicted_class in NON_RECYCLABLE:
            expected_side = "left"
            waste_group = "NON-RECYCLABLE"
        else:
            print()
            print("RESULT: UNKNOWN MODEL LABEL — no disposal suggestion made.")
            return

        print()
        print(f"DECISION: {waste_group}")
        print(f"SUGGESTED COMPARTMENT: {expected_side.upper()}")
        print(
            f"Place the item in the {expected_side.upper()} compartment now. "
            "Waiting for side confirmation..."
        )

        deadline = time.monotonic() + SIDE_CONFIRM_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            side_data = stack.side_detector.detect_once().to_dict()

            left = side_data["leftEvidence"]
            right = side_data["rightEvidence"]
            detected_side = side_data.get("detectedSide")

            print(
                f"SIDE | left_delta={left['deltaCm']} cm | "
                f"right_delta={right['deltaCm']} cm | "
                f"detected={detected_side} | valid={side_data['valid']}"
            )

            if side_data["valid"] and detected_side in ("left", "right"):
                print()
                print(f"ACTUAL PLACEMENT: {detected_side.upper()}")

                if detected_side == expected_side:
                    print("PLACEMENT RESULT: CORRECT")
                else:
                    print(
                        "PLACEMENT RESULT: MISMATCH — "
                        f"AI suggested {expected_side.upper()}."
                    )

                print("Refreshing capacity and traffic lights...")

                capacity_data = stack.capacity_monitor.check_all().to_dict()
                print_capacity("LEFT", capacity_data["left"])
                print_capacity("RIGHT", capacity_data["right"])

                print()
                print("RESULT: PASS — real camera + AI + hardware test completed.")
                print("Note: no dashboard analytics were written by this test.")
                return

            time.sleep(SIDE_POLL_SECONDS)

        print()
        print("RESULT: Camera prediction completed, but disposal side was not confirmed.")
        print("Use a larger/flatter item directly beneath one compartment sensor.")

    except KeyboardInterrupt:
        print("\nTest stopped by user.")

    finally:
        if camera is not None:
            try:
                camera.stop()
            except Exception:
                pass

            try:
                camera.close()
            except Exception:
                pass

        if stack is not None:
            stack.close()

        print("Camera stopped. GPIO resources released; traffic lights are OFF.")


if __name__ == "__main__":
    main()

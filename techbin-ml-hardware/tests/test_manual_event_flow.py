from app.camera.capture import CameraCaptureService
from app.telemetry.payloads import build_event_payload
from app.utils.event_logger import save_event_log

print("Starting camera...")
camera = CameraCaptureService()
camera.start()

print("Capturing test image...")
image_path = camera.capture_image(prefix="manual_event")
camera.stop()

print(f"Image captured: {image_path}")

predicted_class = input("Enter predicted class (cardboard/glass/metal/paper/plastic/trash): ").strip().lower()
confidence = float(input("Enter confidence (example 0.91): ").strip())
disposal_side = input("Enter disposal side (left/right): ").strip().lower()

payload = build_event_payload(
    predicted_class=predicted_class,
    confidence=confidence,
    image_path=image_path,
    disposal_side=disposal_side,
)

log_path = save_event_log(payload)

print("\nEvent created successfully.")
print(f"Log saved at: {log_path}")
print("\nPayload:")
print(payload)

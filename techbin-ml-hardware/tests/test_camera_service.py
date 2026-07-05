from app.camera.capture import CameraCaptureService

camera = CameraCaptureService()

print("Starting camera service...")
camera.start()

image_path = camera.capture_image(prefix="service_test")
print(f"Image saved at: {image_path}")

camera.stop()
print("Camera service stopped.")
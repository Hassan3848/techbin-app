#!/usr/bin/env python3
"""
Secret-safe TechBin Pi demo readiness preflight.

This script checks configuration presence, model package files, metal override
enablement, local env-file permissions, and telemetry queue backlog. It does
not initialize GPIO, open the camera, contact Supabase, or print secret values.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = ROOT / ".env.local"
MODEL_FILE = "techbin_effnetv2_camera_dynamic_range.tflite"
LABELS_FILE = "labels.json"
PREPROCESSING_FILE = "preprocessing_config.json"
REQUIRED_ENV = (
    "TECHBIN_SUPABASE_URL",
    "TECHBIN_ORG_ID",
    "TECHBIN_BIN_CODE",
    "TECHBIN_DEVICE_TOKEN",
    "TECHBIN_MODEL_PACKAGE_PATH",
    "TECHBIN_MODEL_VERSION",
)


def mask_status(value: str | None) -> str:
    return "set" if value and value.strip() else "missing"


def load_env_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return True, "not_found"

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        return False, f"bad_permissions:{mode:o}"

    with path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            if name and name not in os.environ:
                os.environ[name] = value.strip().strip("'\"")

    return True, "loaded"


def check_file(path: Path) -> str:
    return "ok" if path.exists() and path.is_file() else "missing"


def main() -> int:
    env_path = Path(os.getenv("TECHBIN_LOCAL_ENV_FILE", str(DEFAULT_ENV_PATH))).expanduser()
    env_ok, env_status = load_env_file(env_path)

    model_package_raw = os.getenv("TECHBIN_MODEL_PACKAGE_PATH", "").strip()
    model_package = Path(model_package_raw).expanduser() if model_package_raw else None
    pending_dir = ROOT / "logs" / "telemetry_queue" / "pending"
    pending_count = len(list(pending_dir.glob("*.json"))) if pending_dir.exists() else 0
    metal_override = os.getenv("TECHBIN_ENABLE_METAL_OVERRIDE", "").strip().lower()
    metal_override_ok = metal_override in {"1", "true", "yes", "on"}

    checks: list[tuple[str, bool, str]] = [
        (".env.local", env_ok, env_status),
        ("TECHBIN_ENABLE_METAL_OVERRIDE", metal_override_ok, "set_to_1" if metal_override_ok else "not_set_to_1"),
        ("telemetry_queue_pending_count", True, str(pending_count)),
    ]

    for name in REQUIRED_ENV:
        value = os.getenv(name)
        checks.append((name, bool(value and value.strip()), mask_status(value)))

    if model_package is None:
        checks.extend(
            [
                (MODEL_FILE, False, "model_package_missing"),
                (LABELS_FILE, False, "model_package_missing"),
                (PREPROCESSING_FILE, False, "model_package_missing"),
            ]
        )
    else:
        checks.extend(
            [
                (MODEL_FILE, (model_package / MODEL_FILE).is_file(), check_file(model_package / MODEL_FILE)),
                (LABELS_FILE, (model_package / LABELS_FILE).is_file(), check_file(model_package / LABELS_FILE)),
                (
                    PREPROCESSING_FILE,
                    (model_package / PREPROCESSING_FILE).is_file(),
                    check_file(model_package / PREPROCESSING_FILE),
                ),
            ]
        )

    print("TechBin Pi demo readiness preflight")
    print(f"root={ROOT}")
    print(f"env_file={env_path}")
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"{status:4} {name}: {detail}")

    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

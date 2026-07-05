"""
Permanent real-device TechBin runtime entrypoint.

Run one real disposal session:
    python3 -m app.main_real_device

By default this captures real hardware, updates local totals, and uses the
existing telemetry queue with Supabase upload-or-queue behavior.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.config import ensure_runtime_directories
from app.engine.real_device_pipeline import (
    RealDeviceDisposalPipeline,
    RealDevicePipelineConfig,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one real TechBin Pi disposal session."
    )
    parser.add_argument(
        "--telemetry-mode",
        choices=("none", "queue", "upload_or_queue"),
        default="upload_or_queue",
        help="Supabase telemetry handling mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full result JSON.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    ensure_runtime_directories()

    config = RealDevicePipelineConfig(telemetry_mode=args.telemetry_mode)
    pipeline = RealDeviceDisposalPipeline(config=config)
    result = pipeline.process_once()

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"status={result.status}")
        print(f"processed={result.processed}")
        print(f"eventId={result.eventId}")
        print(f"logPath={result.logPath}")
        print(f"telemetry={result.telemetry}")
        if result.faultCode:
            print(f"faultCode={result.faultCode}")
        print(result.message)

    return 0 if result.processed else 1


if __name__ == "__main__":
    sys.exit(main())

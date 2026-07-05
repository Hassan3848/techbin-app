#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR"

RUN_CAMERA_TESTS="${TECHBIN_RUN_CAMERA_TESTS:-0}"

echo
echo "================================================="
echo " TechBin Foundation Test Runner"
echo "================================================="
echo "Project root: $ROOT_DIR"
echo "PYTHONPATH  : $PYTHONPATH"
echo "Camera tests: $RUN_CAMERA_TESTS"
echo "================================================="
echo

run_test() {
  local test_file="$1"

  echo
  echo "-------------------------------------------------"
  echo "Running: $test_file"
  echo "-------------------------------------------------"

  python3 "$test_file"

  echo
  echo "PASS: $test_file"
}

run_test "tests/test_labels_validator.py"
run_test "tests/test_preprocess.py"
run_test "tests/test_confidence_engine.py"
run_test "tests/test_telemetry_uploader.py"
run_test "tests/test_fault_reporter.py"
run_test "tests/test_health_monitor.py"
run_test "tests/test_event_processor.py"

if [[ "$RUN_CAMERA_TESTS" == "1" ]]; then
  echo
  echo "Camera tests enabled."
  echo "Make sure the camera is connected before running this."
  run_test "tests/test_camera_service.py"
else
  echo
  echo "Skipping live camera tests."
  echo "To run camera tests:"
  echo "  TECHBIN_RUN_CAMERA_TESTS=1 ./scripts/run_foundation_tests.sh"
fi

echo
echo "================================================="
echo " All selected TechBin foundation tests passed."
echo "================================================="

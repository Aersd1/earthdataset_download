#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -u download_region.py wb --dataset era5 \
  --lat "${LAT:-36.3}" --lon "${LON:-120.33}" --radius-km "${RADIUS_KM:-50}" \
  --start "${START:-2020-01-01}" --end "${END:-2020-01-01}" \
  --out "${OUT:-downloads/era5_region}" "$@"

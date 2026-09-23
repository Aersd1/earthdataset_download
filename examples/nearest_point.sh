#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# One day by default. Dates, location and output can be overridden via environment.
exec .venv/bin/python -u download_region.py wb --dataset era5 \
  --lat "${LAT:-36.3}" --lon "${LON:-120.33}" --point \
  --start "${START:-2020-01-01}" --end "${END:-2020-01-01}" \
  --csv --out "${OUT:-downloads/era5_nearest}" "$@"

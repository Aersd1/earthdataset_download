#!/usr/bin/env bash
# Run on the Linux download server. Existing ~/.cdsapirc is used automatically.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
args=(era5 --point --lat "${LAT:-36.3}" --lon "${LON:-120.33}"
      --group "${GROUP:-surface}" --out "${OUT:-downloads/era5_nearest}")
if [[ -n "${DATE:-}" ]]; then
  if [[ -n "${START:-}" || -n "${END:-}" ]]; then
    echo 'DATE cannot be combined with START/END.' >&2
    exit 2
  fi
  args+=(--date "$DATE")
elif [[ -n "${START:-}" ]]; then
  args+=(--start "$START")
  if [[ -n "${END:-}" ]]; then
    args+=(--end "$END")
  fi
else
  echo 'Set DATE=2025-01-01 for a sample, or START=2025 to download through latest availability.' >&2
  exit 2
fi
exec "${PYTHON_BIN:-.venv/bin/python}" -u download_region.py "${args[@]}" "$@"

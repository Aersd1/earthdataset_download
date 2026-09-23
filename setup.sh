#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python_bin="${PYTHON_BIN:-python3}"
"$python_bin" -c 'import sys; sys.exit("Python 3.11 or newer is required") if sys.version_info < (3, 11) else None'
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -p 'test_*.py' -v
printf '\nReady. Run: .venv/bin/python download_region.py --help\n'

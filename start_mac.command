#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo 'First run: follow the macOS setup steps in README.md.'
  exit 1
fi
exec .venv/bin/python -m bigdelta

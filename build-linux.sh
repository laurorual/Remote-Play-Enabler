#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv-build
. .venv-build/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt

rm -rf build dist
python -m PyInstaller --clean --noconfirm RemotePlayEnabler.spec

echo
echo "Build complete:"
echo "  dist/RemotePlayEnabler"

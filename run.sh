#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install / sync dependencies
pip install -q -r requirements.txt

PORT="${PORT:-5002}"

# Kill anything already on the port
echo "Checking port ${PORT}..."
lsof -ti:"${PORT}" | xargs kill -9 2>/dev/null || true

echo "Starting CampingPro on http://127.0.0.1:${PORT}"
python run.py

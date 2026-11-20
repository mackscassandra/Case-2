#!/usr/bin/env bash
# Start the Big 4 recommender app:  ./run_app.sh [port]
# First run creates .venv and installs what the app needs; later runs start right away.
# Reads only data/processed/ and data/manual/ (no API keys or network needed).
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8501}"

if [ ! -d .venv ]; then
  echo "Setting up .venv (first run only)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Reinstall only when the requirements file changed.
STAMP=.venv/.app-requirements.sha
SUM=$(cat requirements.txt requirements-app.txt | sha256sum | cut -d' ' -f1)
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$SUM" ]; then
  pip install -q -r requirements.txt -r requirements-app.txt
  echo "$SUM" > "$STAMP"
fi

if [ ! -f data/processed/zip_features.parquet ] || [ ! -f data/processed/metro_features.parquet ]; then
  echo "Note: data/processed/ has no feature tables yet, so the app will show demo data."
  echo "      Build them with: python ingest/run_all.py"
fi

echo "Starting the app at http://localhost:$PORT  (Ctrl+C to stop)"
exec streamlit run app/streamlit_app.py --server.port "$PORT"

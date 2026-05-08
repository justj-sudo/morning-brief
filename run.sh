#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Morning Brief — Local Runner
#  Usage: ./run.sh
#  Requires environment variables set (see .env.example)
# ─────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if it exists (local dev only — never commit .env)
if [ -f ".env" ]; then
  echo "📂 Loading .env..."
  export $(grep -v '^#' .env | xargs)
fi

# Check required keys
REQUIRED_VARS=(ANTHROPIC_API_KEY ALPACA_API_KEY ALPACA_SECRET_KEY PERPLEXITY_API_KEY)
MISSING=0
for VAR in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!VAR}" ]; then
    echo "❌ Missing: $VAR"
    MISSING=1
  fi
done

if [ "$MISSING" -eq 1 ]; then
  echo ""
  echo "Set missing variables in .env or export them before running."
  echo "See .env.example for the template."
  exit 1
fi

# Install deps if needed
if ! python3 -c "import requests" &>/dev/null; then
  echo "📦 Installing dependencies..."
  pip install -r requirements.txt -q
fi

echo ""
python3 scripts/generate_brief.py

# Auto-open HTML in browser (macOS / Linux)
TODAY=$(date +%Y-%m-%d)
HTML_FILE="output/brief_${TODAY}.html"

if [ -f "$HTML_FILE" ]; then
  if command -v open &>/dev/null; then
    open "$HTML_FILE"                    # macOS
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$HTML_FILE"               # Linux
  fi
fi

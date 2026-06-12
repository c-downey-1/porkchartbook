#!/usr/bin/env bash
# update_pork_chartbook.sh — daily pork chartbook update.
#
# Probes long-term sources, ingests short-term (AMS) daily, rebuilds
# docs/data.json, pushes to GitHub when data changed, and emails a summary.
# All orchestration logic lives in porkchartbook.orchestrate; this wrapper just
# sets up the environment for launchd (which has a minimal env) and logs.
#
# Driven by launchd: ~/Library/LaunchAgents/com.innovateanimalag.porkchartbook.plist

set -uo pipefail

# Resolve the project dir from this script's own location so nothing
# machine-specific has to be hardcoded (keeps it out of the public repo).
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HOME/pork_chartbook.log"

# Pull exported env vars (NASS_API_KEY, MARS_API_KEY, GMAIL_APP_PASSWORD) from
# the login shell rc without running interactive startup — same pattern as the
# HPAI dashboard job.
eval "$(grep '^export ' "$HOME/.zshrc" 2>/dev/null || true)"

cd "$PROJECT_DIR" || exit 1

echo "========================================" >> "$LOG"
echo "Pork Chartbook Update — $(date)" >> "$LOG"
echo "========================================" >> "$LOG"

# orchestrate.py owns ingest -> build -> commit/push -> email.
# PYTHONPATH=src so `python3 -m porkchartbook.orchestrate` resolves the package.
PYTHONPATH="$PROJECT_DIR/src" python3 -m porkchartbook.orchestrate "$@" >> "$LOG" 2>&1
STATUS=$?

echo "Exit status: $STATUS" >> "$LOG"
echo "" >> "$LOG"
exit $STATUS

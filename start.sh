#!/usr/bin/env bash
# Starts the ShadowMap backend and frontend together in ONE terminal.
# Press Ctrl+C once to stop both.

cd "$(dirname "$0")" || exit 1

for port in 8000 5173; do
  if ss -ltn | grep -q ":$port "; then
    echo "Port $port is already in use — ShadowMap (or something else) is already running."
    echo "Close the other terminal running it, or press Ctrl+C there, then try again."
    exit 1
  fi
done

# When this script stops (Ctrl+C), stop everything it started.
trap 'trap - INT TERM EXIT; echo; echo "Stopping ShadowMap..."; kill 0' INT TERM EXIT

(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &

sleep 3
echo
echo "=============================================="
echo "  ShadowMap is running."
echo "  Open the app:  http://localhost:5173"
echo "  Stop it:       press Ctrl+C in this terminal"
echo "=============================================="
echo
wait

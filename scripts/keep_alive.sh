#!/bin/bash
# Simple keep-alive script to ping Render service every 10 minutes
# Usage: nohup bash scripts/keep_alive.sh &

URL="https://dopamine-detox-backend.onrender.com/health"
INTERVAL=600  # 10 minutes in seconds

echo "$(date) - Keep-alive started. Pinging every ${INTERVAL}s"

while true; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --location "$URL")
  echo "$(date) - Ping response: $STATUS"
  sleep $INTERVAL
done

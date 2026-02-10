#!/usr/bin/env bash
# Start script for Render (and Docker).
# Render injects $PORT; default to 8000 for local/Docker.
exec newrelic-admin run-program uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

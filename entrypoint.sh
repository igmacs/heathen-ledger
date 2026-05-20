#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting Heathen Ledger bot..."
export PYTHONPATH="src:$PYTHONPATH"
exec python -m heathen_ledger.bot

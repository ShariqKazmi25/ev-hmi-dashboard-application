#!/bin/bash
set -e

PROJECT_DIR="/home/pi/car-cluster-hmi"
ENV_FILE="$PROJECT_DIR/deploy/cluster-hmi.env"

cd "$PROJECT_DIR"
export DISPLAY=:0
export PYTHONUNBUFFERED=1

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

exec /usr/bin/python3 main.py --fullscreen

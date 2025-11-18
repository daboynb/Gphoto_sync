#!/bin/bash
# Stop a specific profile
# Usage: ./stop-profile.sh 1

if [ -z "$1" ]; then
    echo "Usage: ./stop-profile.sh <profile_number>"
    echo "Example: ./stop-profile.sh 1"
    exit 1
fi

PROFILE_NUM=$1
COMPOSE_FILE="docker-compose.profile${PROFILE_NUM}.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Error: $COMPOSE_FILE not found!"
    exit 1
fi

echo "Stopping profile ${PROFILE_NUM}..."
docker compose -f "$COMPOSE_FILE" down

echo "✅ Profile ${PROFILE_NUM} stopped!"

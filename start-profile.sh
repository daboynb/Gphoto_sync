#!/bin/bash
# Start a specific profile
# Usage: ./start-profile.sh 1
#        ./start-profile.sh 2

if [ -z "$1" ]; then
    echo "Usage: ./start-profile.sh <profile_number>"
    echo "Example: ./start-profile.sh 1"
    exit 1
fi

PROFILE_NUM=$1
COMPOSE_FILE="docker-compose.profile${PROFILE_NUM}.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Error: $COMPOSE_FILE not found!"
    echo "Available profiles:"
    ls docker-compose.profile*.yml 2>/dev/null || echo "  No profiles found"
    exit 1
fi

# Fix permissions for this profile
if [ -d "profile${PROFILE_NUM}" ]; then
    echo "Fixing permissions for profile${PROFILE_NUM}..."
    sudo chown -R $(id -u):$(id -g) "profile${PROFILE_NUM}" "photos${PROFILE_NUM}" 2>/dev/null || true
    chmod -R 755 "profile${PROFILE_NUM}" "photos${PROFILE_NUM}" 2>/dev/null || true
fi

echo "Starting profile ${PROFILE_NUM}..."
docker compose -f "$COMPOSE_FILE" up -d

echo "✅ Profile ${PROFILE_NUM} started!"
echo "   View logs: docker compose -f $COMPOSE_FILE logs -f"

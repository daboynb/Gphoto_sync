#!/bin/bash
# Stop all services

echo "Stopping all profiles..."
for compose_file in docker-compose.profile*.yml; do
    if [ -f "$compose_file" ]; then
        profile_num=$(echo "$compose_file" | grep -o '[0-9]\+')
        echo "  → Stopping profile ${profile_num}..."
        docker compose -f "$compose_file" down
    fi
done

echo ""
echo "Stopping Web GUI..."
docker compose -f docker-compose.gui.yml down

echo ""
echo "✅ All services stopped!"

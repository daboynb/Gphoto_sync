#!/bin/bash
# Start GUI and all profiles

echo "Starting Web GUI..."
docker compose -f docker-compose.gui.yml up -d

echo ""
echo "Starting all profiles..."
for compose_file in docker-compose.profile*.yml; do
    if [ -f "$compose_file" ]; then
        profile_num=$(echo "$compose_file" | grep -o '[0-9]\+')
        echo "  → Starting profile ${profile_num}..."

        # Fix permissions
        if [ -d "profile${profile_num}" ]; then
            sudo chown -R $(id -u):$(id -g) "profile${profile_num}" "photos${profile_num}" 2>/dev/null || true
            chmod -R 755 "profile${profile_num}" "photos${profile_num}" 2>/dev/null || true
        fi

        docker compose -f "$compose_file" up -d
    fi
done

echo ""
echo "✅ All services started!"
echo "   Web GUI: http://localhost:8080"
echo "   View logs: docker compose -f docker-compose.profile1.yml logs -f"

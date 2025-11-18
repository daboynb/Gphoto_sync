#!/bin/bash
# Start only the Web GUI

docker compose -f docker-compose.gui.yml up -d

echo "✅ Web GUI started at http://localhost:8080"

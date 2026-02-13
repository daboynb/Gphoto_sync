#!/bin/bash

set -e

echo "=== Building all Docker images ==="

echo ""
echo "[1/3] Building gphotos-sync..."
docker build --no-cache -t gphotos-sync .

echo ""
echo "[2/3] Building gphotos-web-gui..."
docker build --no-cache -t gphotos-web-gui ./web-gui

echo ""
echo "[3/3] Building gphotos-auth..."
docker build --no-cache -t gphotos-auth ./auth

echo ""
echo "=== All images built successfully ==="
docker images | grep -E "gphotos-(sync|web-gui|auth)"

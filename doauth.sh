#!/usr/bin/env bash
set -e
set -o pipefail

# If PROFILE_DIR is not set, find the next available profile number
if [ -z "$PROFILE_DIR" ]; then
  PROFILE_NUM=1
  while [ -d "./profile$PROFILE_NUM" ]; do
    PROFILE_NUM=$((PROFILE_NUM + 1))
  done
  PROFILE_DIR="./profile$PROFILE_NUM"
  echo "No PROFILE_DIR specified. Using next available: $PROFILE_DIR"
fi

mkdir -p $PROFILE_DIR

# docker build . --tag gphotos-sync

cd auth
PUID=$(id -u) PGID=$(id -g) PROFILE_DIR="$PROFILE_DIR" docker compose up -d --build

echo "giving VNC time to be ready, please wait..."
sleep 2

echo "=========================================="
echo "Profile directory: $PROFILE_DIR"
echo "=========================================="
echo "Open chrome by using the open-chrome.sh script then close that browser window (inside the container) before continuing"
read -p  "Press any key after you have authenticated in your browser at http://$(hostname):6080"

docker compose down

echo ""
echo "=========================================="
echo "Authentication completed!"
echo "Profile saved to: $PROFILE_DIR"
echo "=========================================="

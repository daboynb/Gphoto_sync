#!/usr/bin/env bash

PROFILE_DIR=${PROFILE_DIR:-./profile}

# Determine download directory based on profile directory
# If PROFILE_DIR is profileN, use photosN
if [[ "$PROFILE_DIR" =~ profile([0-9]+)$ ]]; then
  DOWNLOAD_DIR=${DOWNLOAD_DIR:-./photos${BASH_REMATCH[1]}}
else
  DOWNLOAD_DIR=${DOWNLOAD_DIR:-./photos}
fi

if [ ! -n "$SKIP_DOCKER_BUILD" ]; then
  docker build . --tag gphotos-sync || exit 1
fi

# Fix permissions before starting
mkdir -p "$DOWNLOAD_DIR" "$PROFILE_DIR"
sudo chown -R $(id -u):$(id -g) "$DOWNLOAD_DIR" "$PROFILE_DIR" 2>/dev/null || true
chmod -R 755 "$DOWNLOAD_DIR" "$PROFILE_DIR"

rm -f ${PROFILE_DIR}/Singleton*

echo "=========================================="
echo "Profile: $PROFILE_DIR"
echo "Download to: $DOWNLOAD_DIR"
echo "=========================================="

docker run -it \
    --network host \
    -v ./${PROFILE_DIR}:/tmp/gphotos-cdp \
    -v ./${DOWNLOAD_DIR}:/download \
    ${GPHOTOS_CDP_SRC_ARGS} \
    -e PUID=$(id -u) \
    -e PGID=$(id -g) \
    -e LOGLEVEL=debug \
    --privileged \
    gphotos-sync:latest \
    no-cron

rm -f ${PROFILE_DIR}/Singleton*
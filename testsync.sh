#!/usr/bin/env bash

PROFILE_DIR=${PROFILE_DIR:-./profile}

if [ ! -n "$SKIP_DOCKER_BUILD" ]; then
  docker build . --tag gphotos-sync || exit 1
fi

# Fix permissions before starting
mkdir -p photos profile
sudo chown -R $(id -u):$(id -g) photos profile 2>/dev/null || true
chmod -R 755 photos profile

rm -f ${PROFILE_DIR}/Singleton*

docker run -it \
    --network host \
    -v ./${PROFILE_DIR}:/tmp/gphotos-cdp \
    -v ./photos:/download \
    ${GPHOTOS_CDP_SRC_ARGS} \
    -e PUID=$(id -u) \
    -e PGID=$(id -g) \
    -e LOGLEVEL=debug \
    --privileged \
    gphotos-sync:latest \
    no-cron

rm -f ${PROFILE_DIR}/Singleton*
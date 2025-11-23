#!/bin/bash

source /app/log.sh

pidof cron && (echo "cron is already running" && exit 1)

set -e

CRON_SCHEDULE=${CRON_SCHEDULE:-0 * * * *}

PUID=${PUID:-1001}
PGID=${PGID:-1001}

id abc 2>/dev/null || (
addgroup abc --gid "${PGID}" --quiet
adduser abc --uid "${PUID}" --gid "${PGID}" --disabled-password --gecos "" --quiet
)

info "running with user uid: $(id -u abc) and user gid: $(id -g abc)"
info "Image version: ${IMAGE_VERSION:-unknown} | Built: ${BUILD_DATE:-unknown}"

# Ensure download and profile directories exist and have correct permissions
DOWNLOAD_DIR="${DOWNLOAD_DIR:-/download}"
PROFILE_DIR="${PROFILE_DIR:-/tmp/gphotos-cdp}"

# Create all needed directories
mkdir -p "$DOWNLOAD_DIR" "$DOWNLOAD_DIR/tmp" "$PROFILE_DIR"

# Set ownership and permissions
# For mounted volumes, we need to ensure the user inside the container can write
if ! chown -R abc:abc "$DOWNLOAD_DIR" "$PROFILE_DIR" /app 2>/dev/null; then
    warning "Failed to change ownership of directories. If using custom paths, ensure host directories are owned by UID:GID ${PUID}:${PGID}"
fi

if ! chmod -R 755 "$DOWNLOAD_DIR" "$PROFILE_DIR" 2>/dev/null; then
    warning "Failed to change permissions of directories. Some operations may fail."
fi

# Ensure Profile directory subdirectories exist and are writable
mkdir -p "$PROFILE_DIR/Default" 2>/dev/null || true
chown -R abc:abc "$PROFILE_DIR/Default" 2>/dev/null || true
chmod -R 755 "$PROFILE_DIR/Default" 2>/dev/null || true

info "download dir permissions: $(ls -ld $DOWNLOAD_DIR)"
info "profile dir permissions: $(ls -ld $PROFILE_DIR)"

# Verify that abc user can actually write to profile directory
if ! sudo -u abc test -w "$PROFILE_DIR"; then
    warning "Profile directory $PROFILE_DIR is not writable by user abc (UID ${PUID})"
    warning "This may cause login issues. Please run on host: sudo chown -R ${PUID}:${PGID} <your_custom_profile_path>"
fi

if [[ "$1" == 'no-cron' ]]; then
    sudo -E -u abc sh /app/sync.sh
else
    info "scheduling cron job for: $CRON_SCHEDULE"
    LOGFIFO='/var/log/cron.fifo'
    if [[ ! -e "$LOGFIFO" ]]; then
        mkfifo "$LOGFIFO"
    fi
    chmod a+rw $LOGFIFO

    (while true; do cat "$LOGFIFO" || sleep 0.2; done) &

    # Run sync immediately on startup if RUN_ON_STARTUP is set
    if [[ "$RUN_ON_STARTUP" == "true" ]] || [[ "$RUN_ON_STARTUP" == "1" ]]; then
        info "running initial sync on startup..."
        sudo -E -u abc sh /app/sync.sh > "$LOGFIFO" 2>&1
        info "initial sync completed, starting cron scheduler..."
    fi

    CRON="CHROMIUM_USER_FLAGS='--no-sandbox'"
    CRON="$CRON\nHEALTHCHECK_ID='$HEALTHCHECK_ID'"
    CRON="$CRON\nHEALTHCHECK_HOST='$HEALTHCHECK_HOST'"
    CRON="$CRON\nLOGLEVEL='$LOGLEVEL'"
    CRON="$CRON\nWORKER_COUNT='$WORKER_COUNT'"
    CRON="$CRON\nGPHOTOS_CDP_ARGS='$GPHOTOS_CDP_ARGS'"
    CRON="$CRON\nALBUMS='$ALBUMS'"
    CRON="$CRON\nGPHOTOS_LOCALE_FILE='$GPHOTOS_LOCALE_FILE'"
    CRON="$CRON\nDOWNLOAD_DIR='$DOWNLOAD_DIR'"
    CRON="$CRON\nPROFILE_DIR='$PROFILE_DIR'"
    CRON="$CRON\n$CRON_SCHEDULE /usr/bin/flock -n /app/sync.lock bash /app/sync.sh > $LOGFIFO 2>&1"

    if [ -n "$RESTART_SCHEDULE" ]; then
        CRON="$CRON\n$RESTART_SCHEDULE rm -f /download/.lastdone* && rm -f /download/**/.lastdone* && echo \"Deleting .lastdone to restart schedule\" > $LOGFIFO 2>&1"
    fi

    echo -e "$CRON" | crontab -u abc -
    cron -f
fi

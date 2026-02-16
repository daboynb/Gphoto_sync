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

# Detect if ALBUMS configuration changed - if so, clean .lastdone files
ALBUMS_CONFIG_FILE="$PROFILE_DIR/.albums_config"
CURRENT_ALBUMS="${ALBUMS:-ALL}"

if [ -f "$ALBUMS_CONFIG_FILE" ]; then
    PREVIOUS_ALBUMS=$(cat "$ALBUMS_CONFIG_FILE" 2>/dev/null || echo "")
    if [ "$PREVIOUS_ALBUMS" != "$CURRENT_ALBUMS" ]; then
        info "Albums configuration changed from '$PREVIOUS_ALBUMS' to '$CURRENT_ALBUMS'"
        info "Cleaning sync state files to force full re-sync..."

        # Clean .lastdone files (for ALL sync and subdirectories)
        rm -f "$DOWNLOAD_DIR/.lastdone"* 2>/dev/null || true
        find "$DOWNLOAD_DIR" -name ".lastdone*" -type f -delete 2>/dev/null || true

        # Clean .downloaded_ids.txt files (tracks which photos were downloaded)
        rm -f "$DOWNLOAD_DIR/.downloaded_ids.txt" 2>/dev/null || true
        find "$DOWNLOAD_DIR" -name ".downloaded_ids.txt" -type f -delete 2>/dev/null || true

        info "Cleanup completed - full sync will run"
    fi
else
    info "First run or no previous albums config found"
fi

# Save current albums configuration
echo "$CURRENT_ALBUMS" > "$ALBUMS_CONFIG_FILE"
chown abc:abc "$ALBUMS_CONFIG_FILE" 2>/dev/null || true

# Verify that abc user can actually write to profile directory
if ! sudo -u abc test -w "$PROFILE_DIR"; then
    warning "Profile directory $PROFILE_DIR is not writable by user abc (UID ${PUID})"
    warning "This may cause login issues. Please run on host: sudo chown -R ${PUID}:${PGID} <your_custom_profile_path>"
fi

# Start VNC display stack if enabled
if [ "${ENABLE_VNC}" = "true" ]; then
    DISPLAY=:99
    export DISPLAY

    info "Starting VNC display stack (Xvfb + x11vnc + noVNC)..."

    # Start virtual display
    Xvfb :99 -screen 0 1920x1080x24 -ac &

    # Start VNC server (no password, shared access)
    x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &

    # Start noVNC websocket proxy
    websockify --web /usr/share/novnc/ 6080 localhost:5900 &

    sleep 1
    info "VNC display stack started (noVNC on port 6080)"
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
    CRON="$CRON\nENABLE_VNC='${ENABLE_VNC:-}'"
    CRON="$CRON\nDISPLAY='${DISPLAY:-}'"
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

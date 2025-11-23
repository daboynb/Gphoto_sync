#!/bin/bash

. /app/log.sh

info "starting sync.sh, pid: $$"

if [ -n "$HEALTHCHECK_ID" ]; then
  curl -sS -X POST -o /dev/null "$HEALTHCHECK_HOST/$HEALTHCHECK_ID/start"
fi

set -e

PROFILE_DIR="${PROFILE_DIR:-/tmp/gphotos-cdp}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-/download}"
WORKER_COUNT=${WORKER_COUNT:-6}
LOGLEVEL=${LOGLEVEL:-info}
GPHOTOS_CDP_ARGS="-profile \"$PROFILE_DIR\" -headless -json -loglevel $LOGLEVEL -removed -workers $WORKER_COUNT $GPHOTOS_CDP_ARGS -run /app/postdl.sh"

# Ensure profile directory is writable before attempting to remove lock files
if [ -w "$PROFILE_DIR" ]; then
  rm -f "$PROFILE_DIR"/Singleton* 2>/dev/null || true
else
  warning "Profile directory $PROFILE_DIR is not writable, cannot remove Singleton lock files"
fi

# Force English language in Chrome preferences
PREFS_FILE="$PROFILE_DIR/Default/Preferences"
if [ -f "$PREFS_FILE" ] && [ -w "$PREFS_FILE" ]; then
  jq '.intl.accept_languages = "en-US,en"' "$PREFS_FILE" > "$PREFS_FILE.tmp" && mv "$PREFS_FILE.tmp" "$PREFS_FILE" 2>/dev/null || true
elif [ -f "$PREFS_FILE" ]; then
  warning "Preferences file exists but is not writable, cannot update language settings"
fi

if [ -n "$ALBUMS" ]; then
  for ALBUM in $(echo $ALBUMS | tr ',' ' '); do
    ALBUM_DL_DIR="$DOWNLOAD_DIR/$(basename "$ALBUM")"
    if [ "$ALBUM" = "ALL" ]; then
      eval gphotos-cdp -dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS
    else
      eval gphotos-cdp -dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS -album $ALBUM
    fi
  done
else
  eval gphotos-cdp -dldir "$DOWNLOAD_DIR" $GPHOTOS_CDP_ARGS
fi

info "completed sync.sh, pid: $$"

if [ -n "$HEALTHCHECK_ID" ]; then
  curl -sS -X POST -o /dev/null --fail "$HEALTHCHECK_HOST/$HEALTHCHECK_ID"
fi

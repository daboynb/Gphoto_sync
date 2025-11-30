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
  # Parse albums - supports two formats:
  # New format: name|id,name|id (name is folder name, id is album ID)
  # Legacy format: id1,id2,id3 (id is used as both name and album ID)

  # Save original IFS and set to comma for splitting
  OLD_IFS="$IFS"
  IFS=','

  for ENTRY in $ALBUMS; do
    # Restore IFS for internal operations
    IFS="$OLD_IFS"

    # Trim whitespace
    ENTRY=$(echo "$ENTRY" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    if [ -z "$ENTRY" ]; then
      IFS=','
      continue
    fi

    # Check if entry contains pipe separator (new format)
    case "$ENTRY" in
      *"|"*)
        # New format: name|id - use cut for POSIX compatibility
        ALBUM_NAME=$(echo "$ENTRY" | cut -d'|' -f1)
        ALBUM_ID=$(echo "$ENTRY" | cut -d'|' -f2)
        ;;
      *)
        # Legacy format: just id (use id as name)
        ALBUM_NAME="$ENTRY"
        ALBUM_ID="$ENTRY"
        ;;
    esac

    ALBUM_DL_DIR="$DOWNLOAD_DIR/$ALBUM_NAME"

    if [ "$ALBUM_ID" = "ALL" ]; then
      eval gphotos-cdp -dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS
    else
      info "Syncing album '$ALBUM_NAME' (ID: $ALBUM_ID) to $ALBUM_DL_DIR"
      eval gphotos-cdp -dldir "$ALBUM_DL_DIR" $GPHOTOS_CDP_ARGS -album "$ALBUM_ID"
    fi

    # Reset IFS for next iteration
    IFS=','
  done

  # Restore original IFS
  IFS="$OLD_IFS"
else
  eval gphotos-cdp -dldir "$DOWNLOAD_DIR" $GPHOTOS_CDP_ARGS
fi

# Cleanup empty tmp directories created by Chrome during download
info "Cleaning up temporary directories..."
find "$DOWNLOAD_DIR" -type d -name "tmp" -empty -delete 2>/dev/null || true
# Also remove non-empty tmp dirs (they should only contain partial downloads)
find "$DOWNLOAD_DIR" -type d -name "tmp" -exec rm -rf {} + 2>/dev/null || true

info "completed sync.sh, pid: $$"

if [ -n "$HEALTHCHECK_ID" ]; then
  curl -sS -X POST -o /dev/null --fail "$HEALTHCHECK_HOST/$HEALTHCHECK_ID"
fi

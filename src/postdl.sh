#!/bin/bash

source /app/log.sh

if [ -z "$1" ];then
  error "file argument required"
  exit 1
fi

# skip .avi files
if [ "${1##*.}" = "avi" ]; then
  debug "skipping date update in exif data for $(basename "$1"), exiftool does not support this file"
  exit 0
fi

# Run exiftool and capture only stderr
result=$(exiftool "-datetimeoriginal<FileModifyDate" -P -overwrite_original_in_place -if 'not $DateTimeOriginal or ($datetimeoriginal gt ${filemodifydate;ShiftTime("1 0")}) or ($filemodifydate gt ${datetimeoriginal;ShiftTime("1 0")})' "$1" 2>&1 >/dev/null)

# If exit code is 2, it just means that this operation didn't make any change. Other exit codes should be propagated
status=$?
if [ $status -eq 2 ]; then
  debug "file already has date in exif data: $(basename "$1")"
elif [ $status -ne 0 ]; then
  # ignore error if result contains "too large" or "invalid atom size"
  if [[ "$result" == *"too large"* || "$result" == *"invalid atom size"* ]]; then
    debug "skipping date update in exif data for $(basename "$1"), exiftool does not support this file"
  fi
  while read line; do
    error "exiftool: $line"
  done <<< "$result"
else
  info "updated date in exif data for $(basename "$1") to match date in Google Photos"
fi
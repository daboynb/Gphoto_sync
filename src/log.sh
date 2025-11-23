#!/bin/bash

# supported log levels: error, warn, info, debug, trace (fatal, panic are aliases for error)
_LOGLEVEL=$(echo ${LOGLEVEL:-info} | tr '[:upper:]' '[:lower:]')

if [ "$_LOGLEVEL" = "fatal" ] || [ "$_LOGLEVEL" = "panic" ]; then
  _LOGLEVEL=error
fi

if [ "$_LOGLEVEL" != "error" ] && [ "$_LOGLEVEL" != "warn" ] && [ "$_LOGLEVEL" != "info" ] && [ "$_LOGLEVEL" != "debug" ] && [ "$_LOGLEVEL" != "trace" ]; then
  echo "Invalid log level: $_LOGLEVEL, defaulting to info"
  _LOGLEVEL=info
fi

_LOGLEVELNUM=$(case $_LOGLEVEL in error) echo 3;; warn) echo 2;; info) echo 1;; debug) echo 0;; trace) echo -1;; esac)

log() {
  if [ "$_LOGLEVEL" != "error" ] && [ "$_LOGLEVEL" != "warn" ] && [ "$_LOGLEVEL" != "info" ] && [ "$_LOGLEVEL" != "debug" ] && [ "$_LOGLEVEL" != "trace" ]; then
    error "Invalid log level: $_LOGLEVEL"
    return
  fi
  LEVELNUM=$(case $1 in error) echo 3;; warn) echo 2;; info) echo 1;; debug) echo 0;; trace) echo -1;; esac)
  if [ "$LEVELNUM" -lt "$_LOGLEVELNUM" ]; then
    return
  fi

  # Use jq to print log with format: {"level": "info", "message": "message", "dt": "2023-01-01T00:00:00.000Z"}
  jq -n -R -c -M -r --arg level "$1" --arg message "$2" '{ "level": $level, "message": $message, "dt": (now | todate) }'
}

error() {
  log error "$1"
}

warn() {
  log warn "$1"
}

info() {
  log info "$1"
}

debug() {
  log debug "$1"
}

trace() {
  log trace "$1"
}
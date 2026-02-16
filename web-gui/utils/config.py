#!/usr/bin/env python3
"""Centralized configuration constants for the web GUI."""
import os

# Timezone
DEFAULT_TIMEZONE = 'Europe/Rome'

# Cron / scheduling
DEFAULT_CRON_SCHEDULE = '0 3 * * *'

# Sync engine defaults
DEFAULT_WORKER_COUNT = 6
DEFAULT_LOGLEVEL = 'info'
DEFAULT_RUN_ON_STARTUP = True

# User / group IDs
DEFAULT_PUID = int(os.getenv('PUID', '1000'))
DEFAULT_PGID = int(os.getenv('PGID', '1000'))

# VNC auth container
DEFAULT_VNC_URL = 'http://localhost:6080'

# Paths
WORKSPACE_PATH = '/workspace'
PROFILES_DIR = os.path.join(WORKSPACE_PATH, 'profiles')
AUTH_DIR = os.path.join(WORKSPACE_PATH, 'auth')
PHOTOS_DIR = os.path.join(WORKSPACE_PATH, 'photos')

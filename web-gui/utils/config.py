#!/usr/bin/env python3
"""Centralized configuration constants for the web GUI."""
import os

# Timezone
DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'Europe/Rome')

# Cron / scheduling
DEFAULT_CRON_SCHEDULE = os.getenv('DEFAULT_CRON_SCHEDULE', '0 3 * * *')

# Sync engine defaults
DEFAULT_WORKER_COUNT = int(os.getenv('DEFAULT_WORKER_COUNT', '6'))
DEFAULT_LOGLEVEL = os.getenv('DEFAULT_LOGLEVEL', 'info')
DEFAULT_RUN_ON_STARTUP = os.getenv('DEFAULT_RUN_ON_STARTUP', 'true').lower() == 'true'

# User / group IDs
DEFAULT_PUID = int(os.getenv('PUID', '1000'))
DEFAULT_PGID = int(os.getenv('PGID', '1000'))

# VNC auth container
DEFAULT_VNC_URL = 'http://localhost:6080'

# VNC viewer for sync containers
DEFAULT_ENABLE_VNC = os.getenv('DEFAULT_ENABLE_VNC', 'false').lower() == 'true'
VNC_PORT_START = int(os.getenv('VNC_PORT_START', '6081'))

# --- Authentication (optional) ---
AUTH_USERNAME = os.getenv('AUTH_USERNAME', '')
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD', '')

# Paths
WORKSPACE_PATH = '/workspace'
PROFILES_DIR = os.path.join(WORKSPACE_PATH, 'profiles')
AUTH_DIR = os.path.join(WORKSPACE_PATH, 'auth')
PHOTOS_DIR = os.path.join(WORKSPACE_PATH, 'photos')

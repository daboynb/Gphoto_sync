#!/usr/bin/env python3
"""Helper functions for Docker container operations."""
import logging
import os

import docker

from utils import config
from utils.cron_helpers import parse_cron_next_run
from utils.docker_client import docker_client
from utils.profile_helpers import extract_profile_name, get_profile_metadata

logger = logging.getLogger(__name__)


def get_container_prefix():
    """Get the container name prefix from environment or default."""
    return os.getenv('CONTAINER_PREFIX', 'gphotos-sync')


def get_sync_containers():
    """Get all gphotos-sync containers."""
    prefix = get_container_prefix()
    containers = docker_client.containers.list(all=True, filters={'name': prefix})
    return containers


def check_sync_status(container):
    """Check if the container has completed sync by looking at logs."""
    try:
        if container.status != 'running':
            return 'stopped'

        logs = container.logs(tail=100).decode('utf-8', errors='ignore')

        if 'SYNC COMPLETED' in logs:
            return 'completed'

        if 'downloading' in logs.lower() or 'processing' in logs.lower() or 'navigating' in logs.lower():
            return 'syncing'

        return 'idle'
    except docker.errors.APIError as exc:
        logger.warning("Could not get sync status for %s: %s", container.name, exc)
        return 'unknown'


def get_container_info(container):
    """Extract relevant info from container."""
    env_vars = {}
    if container.attrs.get('Config', {}).get('Env'):
        for env in container.attrs['Config']['Env']:
            if '=' in env:
                key, val = env.split('=', 1)
                env_vars[key] = val

    cmd = container.attrs.get('Config', {}).get('Cmd', [])
    has_cron = not (cmd and 'no-cron' in cmd)

    if has_cron and env_vars.get('CRON_SCHEDULE'):
        tz = env_vars.get('TZ', config.DEFAULT_TIMEZONE)
        cron_info = parse_cron_next_run(
            env_vars.get('CRON_SCHEDULE', config.DEFAULT_CRON_SCHEDULE), tz
        )
    else:
        cron_info = {'next_run': 'Disabled (no-cron mode)', 'time_until': 'N/A'}

    prefix = get_container_prefix()
    profile_name = extract_profile_name(container.name, prefix)

    metadata = get_profile_metadata(profile_name)
    display_name = metadata.get('display_name', profile_name)

    sync_status = check_sync_status(container)

    # Check VNC status
    vnc_enabled = env_vars.get('ENABLE_VNC', '').lower() == 'true'
    vnc_port = None
    if vnc_enabled:
        # Extract host VNC port from container port bindings
        ports = container.attrs.get('NetworkSettings', {}).get('Ports', {}) or {}
        binding = ports.get('6080/tcp')
        if binding and len(binding) > 0:
            try:
                vnc_port = int(binding[0].get('HostPort', 0))
            except (ValueError, TypeError):
                pass

    return {
        'id': container.id[:12],
        'name': container.name,
        'profile': profile_name,
        'display_name': display_name,
        'status': container.status,
        'state': container.attrs['State']['Status'],
        'created': container.attrs['Created'],
        'cron_schedule': env_vars.get('CRON_SCHEDULE', 'N/A'),
        'run_on_startup': env_vars.get('RUN_ON_STARTUP', 'false'),
        'loglevel': env_vars.get('LOGLEVEL', config.DEFAULT_LOGLEVEL),
        'worker_count': env_vars.get('WORKER_COUNT', str(config.DEFAULT_WORKER_COUNT)),
        'next_run': cron_info['next_run'],
        'time_until': cron_info['time_until'],
        'sync_status': sync_status,
        'vnc_enabled': vnc_enabled,
        'vnc_port': vnc_port,
    }

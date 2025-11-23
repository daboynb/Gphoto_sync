#!/usr/bin/env python3
"""Helper functions for Docker container operations"""
import os
from utils.docker_client import docker_client
from utils.profile_helpers import get_profile_metadata
from utils.cron_helpers import parse_cron_next_run


def get_container_prefix():
    """Get the container name prefix from environment or default"""
    return os.getenv('CONTAINER_PREFIX', 'gphotos-sync')


def get_sync_containers():
    """Get all gphotos-sync containers"""
    prefix = get_container_prefix()
    containers = docker_client.containers.list(all=True, filters={'name': prefix})
    return containers


def check_sync_status(container):
    """Check if the container has completed sync by looking at logs"""
    try:
        # If container is not running, return stopped
        if container.status != 'running':
            return 'stopped'

        # Get last 100 lines of logs (enough to find SYNC COMPLETED)
        logs = container.logs(tail=100).decode('utf-8', errors='ignore')

        # Check if SYNC COMPLETED appears in logs
        if 'SYNC COMPLETED' in logs:
            return 'completed'

        # Check if sync is running (look for specific log patterns)
        if 'downloading' in logs.lower() or 'processing' in logs.lower() or 'navigating' in logs.lower():
            return 'syncing'

        # If container is running but no clear indication
        return 'idle'
    except Exception as e:
        # If we can't get logs, return unknown
        return 'unknown'


def get_container_info(container):
    """Extract relevant info from container"""
    env_vars = {}
    if container.attrs.get('Config', {}).get('Env'):
        for env in container.attrs['Config']['Env']:
            if '=' in env:
                key, val = env.split('=', 1)
                env_vars[key] = val

    # Check if container is running with no-cron command
    cmd = container.attrs.get('Config', {}).get('Cmd', [])
    has_cron = not (cmd and 'no-cron' in cmd)

    # Only calculate next run if cron is enabled
    if has_cron and env_vars.get('CRON_SCHEDULE'):
        # Get timezone from container env, default to Europe/Rome
        tz = env_vars.get('TZ', 'Europe/Rome')
        cron_info = parse_cron_next_run(env_vars.get('CRON_SCHEDULE', '0 2 * * *'), tz)
    else:
        cron_info = {'next_run': 'Disabled (no-cron mode)', 'time_until': 'N/A'}

    # Extract profile name from container name (e.g., "gphotos-sync-family" -> "family")
    profile_name = container.name.replace(get_container_prefix() + '-', '', 1)
    if not profile_name:
        profile_name = 'default'

    # Get metadata for display name
    metadata = get_profile_metadata(profile_name)
    display_name = metadata.get('display_name', profile_name)

    # Get sync status
    sync_status = check_sync_status(container)

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
        'loglevel': env_vars.get('LOGLEVEL', 'info'),
        'worker_count': env_vars.get('WORKER_COUNT', '6'),
        'next_run': cron_info['next_run'],
        'time_until': cron_info['time_until'],
        'sync_status': sync_status
    }

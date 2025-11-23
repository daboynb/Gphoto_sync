#!/usr/bin/env python3
"""Helper functions for path and workspace management"""
from utils.docker_client import docker_client


def get_host_workspace_path():
    """Get the real host path that is mounted as /workspace in this container"""
    try:
        # Get our own container info
        container = docker_client.containers.get('gphotos-web-gui')
        for mount in container.attrs['Mounts']:
            if mount['Destination'] == '/workspace':
                return mount['Source']
    except:
        pass
    # Fallback to /workspace if we can't determine (for local dev)
    return '/workspace'

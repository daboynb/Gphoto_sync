#!/usr/bin/env python3
"""Helper functions for path and workspace management."""
import logging

import docker

from utils.docker_client import docker_client

logger = logging.getLogger(__name__)


def get_host_workspace_path():
    """Get the real host path that is mounted as /workspace in this container."""
    try:
        container = docker_client.containers.get('gphotos-web-gui')
        for mount in container.attrs['Mounts']:
            if mount['Destination'] == '/workspace':
                return mount['Source']
    except (docker.errors.NotFound, docker.errors.APIError) as exc:
        logger.warning("Could not determine host workspace path: %s", exc)
    # Fallback to /workspace if we can't determine (for local dev)
    return '/workspace'

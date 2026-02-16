#!/usr/bin/env python3
"""Docker client initialization."""
import logging

import docker

logger = logging.getLogger(__name__)

# Initialize Docker client with explicit socket path
try:
    docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')
except docker.errors.DockerException as e:
    logger.critical("Error connecting to Docker: %s", e)
    docker_client = None

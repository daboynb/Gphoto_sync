#!/usr/bin/env python3
"""Shared Docker subprocess helpers to avoid duplication across routes."""
import logging
import os
import subprocess

from utils import config

logger = logging.getLogger(__name__)


def stop_auth_container():
    """Stop the VNC auth container via docker compose down.

    Returns (success: bool, output: str).
    """
    try:
        result = subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'down'],
            cwd=config.AUTH_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Failed to stop auth container: %s", result.stderr)
        return result.returncode == 0, result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout stopping auth container")
        return False, 'Command timed out'
    except OSError as exc:
        logger.error("OS error stopping auth container: %s", exc)
        return False, str(exc)


def start_auth_container(profile_name, host_workspace):
    """Start the VNC auth container for a given profile.

    Returns (success: bool, output: str).
    """
    profile_dir = f'{host_workspace}/profiles/{profile_name}'
    try:
        result = subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'up', '-d', '--force-recreate'],
            cwd=config.AUTH_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                'PROFILE_DIR': profile_dir,
                'PUID': str(config.DEFAULT_PUID),
                'PGID': str(config.DEFAULT_PGID),
            },
        )
        if result.returncode != 0:
            logger.error("Failed to start auth container for %s: %s", profile_name, result.stderr)
        return result.returncode == 0, result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout starting auth container for %s", profile_name)
        return False, 'Command timed out'
    except OSError as exc:
        logger.error("OS error starting auth container for %s: %s", profile_name, exc)
        return False, str(exc)


def compose_up(compose_file):
    """Run docker compose up -d --build for a compose file.

    Returns (success: bool, output: str).
    """
    try:
        result = subprocess.run(
            ['docker', 'compose', '-f', compose_file, 'up', '-d', '--build'],
            cwd=config.WORKSPACE_PATH,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("docker compose up failed for %s: %s", compose_file, result.stderr)
        return result.returncode == 0, result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Timeout running docker compose up for %s", compose_file)
        return False, 'Command timed out'
    except OSError as exc:
        logger.error("OS error running docker compose up for %s: %s", compose_file, exc)
        return False, str(exc)

#!/usr/bin/env python3
import logging
import os

from flask import Blueprint, jsonify

from utils import config
from utils.docker_client import docker_client
from utils.docker_helpers import start_auth_container, stop_auth_container
from utils.path_helpers import get_host_workspace_path
from utils.validators import validate_profile_name

import docker

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


def _launch_auth(profile_name, message):
    """Shared logic for start_auth and reauth_profile."""
    profile_path = os.path.join(config.PROFILES_DIR, profile_name)
    if not os.path.exists(profile_path):
        return jsonify({'error': f'Profile directory {profile_name} not found'}), 404

    # Stop any existing auth container first
    stop_auth_container()

    host_workspace = get_host_workspace_path()
    ok, output = start_auth_container(profile_name, host_workspace)

    if ok:
        logger.info("Auth container started for profile '%s'", profile_name)
        return jsonify({
            'status': 'started',
            'profile_name': profile_name,
            'vnc_url': config.DEFAULT_VNC_URL,
            'message': message,
            'output': output,
        })
    else:
        logger.error("Failed to start auth container for '%s': %s", profile_name, output)
        return jsonify({'error': 'Failed to start VNC container', 'output': output}), 500


@auth_bp.route('/api/check-auth/<profile_name>', methods=['GET'])
@validate_profile_name
def check_auth(profile_name):
    """Check if profile has authentication cookies."""
    cookies_file = os.path.join(config.PROFILES_DIR, profile_name, 'Default', 'Cookies')
    has_cookies = os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0
    return jsonify({'authenticated': has_cookies})


@auth_bp.route('/api/start-auth/<profile_name>', methods=['POST'])
@validate_profile_name
def start_auth(profile_name):
    """Start VNC authentication container for a profile."""
    return _launch_auth(profile_name, f'VNC container started for {profile_name}')


@auth_bp.route('/api/reauth-profile/<profile_name>', methods=['POST'])
@validate_profile_name
def reauth_profile(profile_name):
    """Re-authenticate a running profile by loading it in VNC."""
    return _launch_auth(profile_name, f'VNC container started for re-authentication of {profile_name}')


@auth_bp.route('/api/stop-auth', methods=['POST'])
def stop_auth():
    """Stop VNC authentication container."""
    ok, output = stop_auth_container()
    if ok:
        logger.info("Auth container stopped")
        return jsonify({'status': 'stopped', 'message': 'VNC container stopped', 'output': output})
    else:
        logger.error("Failed to stop auth container: %s", output)
        return jsonify({'error': 'Failed to stop VNC container', 'output': output}), 500


@auth_bp.route('/api/auth-status', methods=['GET'])
def auth_status():
    """Check if VNC auth container is running."""
    try:
        containers = docker_client.containers.list(filters={'name': 'auth'})
        if containers:
            container = containers[0]
            return jsonify({
                'running': container.status == 'running',
                'status': container.status,
                'id': container.id[:12],
            })
        return jsonify({'running': False, 'status': 'not_found'})
    except docker.errors.APIError as exc:
        logger.error("Error checking auth status: %s", exc)
        return jsonify({'error': str(exc)}), 500

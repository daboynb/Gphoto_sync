#!/usr/bin/env python3
import os
import subprocess
from flask import Blueprint, jsonify, request
from utils.docker_client import docker_client
from utils.path_helpers import get_host_workspace_path

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/check-auth/<profile_name>', methods=['GET'])
def check_auth(profile_name):
    """Check if profile has authentication cookies"""
    cookies_file = f'/workspace/profiles/{profile_name}/Default/Cookies'
    has_cookies = os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0
    return jsonify({'authenticated': has_cookies})


@auth_bp.route('/api/start-auth/<profile_name>', methods=['POST'])
def start_auth(profile_name):
    """Start VNC authentication container for a profile"""
    # Check if profile directory exists
    if not os.path.exists(f'/workspace/profiles/{profile_name}'):
        return jsonify({'error': f'Profile directory {profile_name} not found'}), 404

    try:
        # Get PUID and PGID from environment or use defaults
        puid = os.getenv('PUID', '1000')
        pgid = os.getenv('PGID', '1000')

        # Get the host path for the profile
        # Since we're running docker from inside web-gui container,
        # we need to use the host path, not the container path
        host_workspace = get_host_workspace_path()
        profile_dir = f'{host_workspace}/profiles/{profile_name}'

        # IMPORTANT: Stop any existing auth container first to avoid reusing wrong profile
        subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'down'],
            cwd='/workspace/auth',
            capture_output=True,
            timeout=30
        )

        # Start the auth container with correct profile
        # Use --force-recreate to ensure the new PROFILE_DIR is used
        result = subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'up', '-d', '--force-recreate'],
            cwd='/workspace/auth',
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                'PROFILE_DIR': profile_dir,
                'PUID': str(puid),
                'PGID': str(pgid)
            }
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'started',
                'profile_name': profile_name,
                'vnc_url': 'http://localhost:6080',
                'message': f'VNC container started for {profile_name}',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': f'Failed to start VNC container',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/reauth-profile/<profile_name>', methods=['POST'])
def reauth_profile(profile_name):
    """Re-authenticate a running profile by loading it in VNC"""
    # Check if profile directory exists
    if not os.path.exists(f'/workspace/profiles/{profile_name}'):
        return jsonify({'error': f'Profile directory {profile_name} not found'}), 404

    try:
        # Get PUID and PGID from environment or use defaults
        puid = os.getenv('PUID', '1000')
        pgid = os.getenv('PGID', '1000')

        # Get the host path for the profile
        host_workspace = get_host_workspace_path()
        profile_dir = f'{host_workspace}/profiles/{profile_name}'

        # IMPORTANT: Stop any existing auth container first to avoid reusing wrong profile
        subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'down'],
            cwd='/workspace/auth',
            capture_output=True,
            timeout=30
        )

        # Start the auth container with the profile to re-authenticate
        result = subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'up', '-d', '--force-recreate'],
            cwd='/workspace/auth',
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **os.environ,
                'PROFILE_DIR': profile_dir,
                'PUID': str(puid),
                'PGID': str(pgid)
            }
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'started',
                'profile_name': profile_name,
                'vnc_url': 'http://localhost:6080',
                'message': f'VNC container started for re-authentication of {profile_name}',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': f'Failed to start VNC container for re-auth',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/stop-auth', methods=['POST'])
def stop_auth():
    """Stop VNC authentication container"""
    try:
        # Stop the auth container
        result = subprocess.run(
            ['docker', 'compose', '-f', 'docker-compose.yml', 'down'],
            cwd='/workspace/auth',
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'stopped',
                'message': 'VNC container stopped',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': 'Failed to stop VNC container',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/auth-status', methods=['GET'])
def auth_status():
    """Check if VNC auth container is running"""
    try:
        # Check if auth container exists
        containers = docker_client.containers.list(filters={'name': 'auth'})

        if containers:
            container = containers[0]
            return jsonify({
                'running': container.status == 'running',
                'status': container.status,
                'id': container.id[:12]
            })
        else:
            return jsonify({
                'running': False,
                'status': 'not_found'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

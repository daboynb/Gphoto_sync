#!/usr/bin/env python3
import glob
import json
import logging
import os
import shutil
from datetime import datetime

import docker
import yaml
from flask import Blueprint, jsonify, request

from utils import config
from utils.container_helpers import get_container_prefix, get_sync_containers
from utils.docker_client import docker_client
from utils.docker_helpers import compose_up
from utils.path_helpers import get_host_workspace_path
from utils.profile_helpers import (
    extract_profile_name,
    find_next_vnc_port,
    get_profile_metadata,
    sanitize_profile_name,
    save_profile_metadata,
)
from utils.validators import is_valid_cron, validate_profile_name

logger = logging.getLogger(__name__)

profiles_bp = Blueprint('profiles', __name__)


@profiles_bp.route('/api/defaults')
def api_defaults():
    """Return configurable default values for the frontend."""
    return jsonify({
        'timezone': config.DEFAULT_TIMEZONE,
        'cron_schedule': config.DEFAULT_CRON_SCHEDULE,
        'worker_count': config.DEFAULT_WORKER_COUNT,
        'loglevel': config.DEFAULT_LOGLEVEL,
        'run_on_startup': config.DEFAULT_RUN_ON_STARTUP,
        'puid': config.DEFAULT_PUID,
        'pgid': config.DEFAULT_PGID,
        'enable_vnc': config.DEFAULT_ENABLE_VNC,
        'vnc_port_start': config.VNC_PORT_START,
    })


@profiles_bp.route('/api/available-profiles')
def api_available_profiles():
    """Get profiles that exist but don't have running containers."""
    profile_dirs = glob.glob(os.path.join(config.PROFILES_DIR, '*'))

    containers = get_sync_containers()
    prefix = get_container_prefix()
    running_profiles = {extract_profile_name(c.name, prefix) for c in containers}

    available_profiles = []
    for profile_path in profile_dirs:
        profile_name = os.path.basename(profile_path)
        if profile_name in running_profiles:
            continue

        compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')
        metadata = get_profile_metadata(profile_name)
        display_name = metadata.get('display_name', profile_name)

        available_profiles.append({
            'name': profile_name,
            'display_name': display_name,
            'path': profile_path,
            'has_compose': os.path.exists(compose_file),
            'compose_file': f'docker-compose.{profile_name}.yml',
        })

    return jsonify(sorted(available_profiles, key=lambda x: x['display_name']))


@profiles_bp.route('/api/create-compose/<profile_name>', methods=['POST'])
@validate_profile_name
def create_compose(profile_name):
    """Create docker-compose file for a profile with custom configuration."""
    req_config = request.get_json() or {}

    workspace_path = get_host_workspace_path()

    enable_cron = req_config.get('enable_cron', True)
    cron_schedule = req_config.get('cron_schedule', config.DEFAULT_CRON_SCHEDULE)
    run_on_startup = req_config.get('run_on_startup', config.DEFAULT_RUN_ON_STARTUP)
    loglevel = req_config.get('loglevel', config.DEFAULT_LOGLEVEL)
    worker_count = req_config.get('worker_count', config.DEFAULT_WORKER_COUNT)
    albums = req_config.get('albums', '')
    timezone = req_config.get('timezone', config.DEFAULT_TIMEZONE)
    puid = req_config.get('puid', config.DEFAULT_PUID)
    pgid = req_config.get('pgid', config.DEFAULT_PGID)
    photo_dir = req_config.get('photo_dir', '')
    restart_schedule = req_config.get('restart_schedule', '')
    healthcheck_url = req_config.get('healthcheck_url', '')
    enable_vnc = req_config.get('enable_vnc', config.DEFAULT_ENABLE_VNC)

    # Validate cron if provided
    if enable_cron and not is_valid_cron(cron_schedule):
        return jsonify({'error': f'Invalid cron schedule: {cron_schedule}'}), 400

    # Build environment section
    env_vars = [
        f'      - PUID={puid}',
        f'      - PGID={pgid}',
        f'      - LOGLEVEL={loglevel}',
        f'      - TZ={timezone}',
        f'      - WORKER_COUNT={worker_count}',
    ]

    if enable_cron:
        env_vars.insert(2, f'      - CRON_SCHEDULE={cron_schedule}')
        env_vars.insert(3, f'      - RUN_ON_STARTUP={str(run_on_startup).lower()}')

    if albums and albums.strip() and albums.strip().upper() != 'ALL':
        env_vars.append(f'      - ALBUMS={albums.strip()}')

    if restart_schedule and restart_schedule.strip():
        env_vars.append(f'      - RESTART_SCHEDULE={restart_schedule.strip()}')

    if healthcheck_url and healthcheck_url.strip():
        url = healthcheck_url.strip()
        if '/' in url:
            parts = url.rsplit('/', 1)
            healthcheck_host = parts[0] if len(parts) > 1 else 'https://hc-ping.com'
            healthcheck_id = parts[1] if len(parts) > 1 else ''
        else:
            healthcheck_host = 'https://hc-ping.com'
            healthcheck_id = url

        if healthcheck_id:
            env_vars.append(f'      - HEALTHCHECK_HOST={healthcheck_host}')
            env_vars.append(f'      - HEALTHCHECK_ID={healthcheck_id}')

    if enable_vnc:
        env_vars.append('      - ENABLE_VNC=true')

    command_line = "    command: no-cron\n" if not enable_cron else ""

    if photo_dir and photo_dir.strip():
        download_dir = photo_dir.strip()
    else:
        download_dir = f'{workspace_path}/photos/{profile_name}'

    restart_policy = '"no"' if not enable_cron else "unless-stopped"

    # VNC port mapping
    vnc_port = None
    if enable_vnc:
        vnc_port = find_next_vnc_port()
        ports_section = f"""    ports:
      - "{vnc_port}:6080"
"""
    else:
        ports_section = ""

    prefix = get_container_prefix()

    compose_content = f"""services:
  {prefix}-{profile_name}:
    image: {prefix}:latest
    container_name: {prefix}-{profile_name}
{command_line}    restart: {restart_policy}
    privileged: true
{ports_section}    volumes:
      - {workspace_path}/profiles/{profile_name}:/tmp/gphotos-cdp
      - {workspace_path}/gphotos-cdp/months-config.json:/app/months-config.json
      - {download_dir}:/download
    environment:
{chr(10).join(env_vars)}
    networks:
      - gphotos-network

networks:
  gphotos-network:
    external: true
"""

    compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')

    try:
        with open(compose_file, 'w') as f:
            f.write(compose_content)

        save_profile_metadata(profile_name, {
            'photo_dir': photo_dir if photo_dir and photo_dir.strip() else '',
        })

        return jsonify({
            'status': 'created',
            'file': f'docker-compose.{profile_name}.yml',
            'message': f'Docker compose file created for profile {profile_name}',
            'config': req_config,
        })
    except OSError as exc:
        logger.error("Failed to write compose file for '%s': %s", profile_name, exc)
        return jsonify({'error': str(exc)}), 500


@profiles_bp.route('/api/get-config/<profile_name>', methods=['GET'])
@validate_profile_name
def get_config(profile_name):
    """Get current configuration from docker-compose file."""
    compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')

    if not os.path.exists(compose_file):
        return jsonify({'error': 'Docker compose file not found'}), 404

    try:
        with open(compose_file, 'r') as f:
            compose_data = yaml.safe_load(f)

        service_name = f'{get_container_prefix()}-{profile_name}'
        service_config = compose_data.get('services', {}).get(service_name, {})
        env_vars = service_config.get('environment', [])
        command = service_config.get('command', '')

        is_no_cron = command == 'no-cron'

        parsed = {
            'cron_schedule': 'disabled' if is_no_cron else '',
            'run_on_startup': config.DEFAULT_RUN_ON_STARTUP,
            'loglevel': config.DEFAULT_LOGLEVEL,
            'worker_count': config.DEFAULT_WORKER_COUNT,
            'albums': '',
            'timezone': config.DEFAULT_TIMEZONE,
            'puid': config.DEFAULT_PUID,
            'pgid': config.DEFAULT_PGID,
            'restart_schedule': '',
            'healthcheck_url': '',
            'enable_vnc': False,
        }

        healthcheck_host = ''
        healthcheck_id = ''

        for env in env_vars:
            if isinstance(env, str) and '=' in env:
                key, val = env.split('=', 1)
                key = key.strip()
                val = val.strip()

                if key == 'CRON_SCHEDULE':
                    parsed['cron_schedule'] = val
                elif key == 'RUN_ON_STARTUP':
                    parsed['run_on_startup'] = val.lower() == 'true'
                elif key == 'LOGLEVEL':
                    parsed['loglevel'] = val
                elif key == 'WORKER_COUNT':
                    parsed['worker_count'] = int(val)
                elif key == 'ALBUMS':
                    parsed['albums'] = val
                elif key == 'TZ':
                    parsed['timezone'] = val
                elif key == 'PUID':
                    parsed['puid'] = int(val)
                elif key == 'PGID':
                    parsed['pgid'] = int(val)
                elif key == 'RESTART_SCHEDULE':
                    parsed['restart_schedule'] = val
                elif key == 'HEALTHCHECK_HOST':
                    healthcheck_host = val
                elif key == 'HEALTHCHECK_ID':
                    healthcheck_id = val
                elif key == 'ENABLE_VNC':
                    parsed['enable_vnc'] = val.lower() == 'true'

        if healthcheck_host and healthcheck_id:
            parsed['healthcheck_url'] = f"{healthcheck_host}/{healthcheck_id}"

        # Extract photo_dir from volumes
        volumes = service_config.get('volumes', [])
        parsed['photo_dir'] = ''
        for volume in volumes:
            if isinstance(volume, str) and ':/download' in volume:
                host_path = volume.split(':')[0]
                workspace_path = get_host_workspace_path()
                default_path = f'{workspace_path}/photos/{profile_name}'
                if host_path != default_path:
                    parsed['photo_dir'] = host_path
                break

        # Extract VNC port from ports section
        ports = service_config.get('ports', [])
        parsed['vnc_port'] = None
        for port_mapping in ports:
            port_str = str(port_mapping)
            if ':6080' in port_str:
                try:
                    parsed['vnc_port'] = int(port_str.split(':')[0].strip('"'))
                except (ValueError, IndexError):
                    pass
                break

        return jsonify(parsed)
    except (OSError, yaml.YAMLError) as exc:
        logger.error("Error reading config for '%s': %s", profile_name, exc)
        return jsonify({'error': str(exc)}), 500


@profiles_bp.route('/api/start-profile/<profile_name>', methods=['POST'])
@validate_profile_name
def start_profile(profile_name):
    """Start a profile container using docker-compose."""
    compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')

    if not os.path.exists(compose_file):
        return jsonify({'error': f'docker-compose.{profile_name}.yml not found'}), 404

    ok, output = compose_up(compose_file)
    if ok:
        logger.info("Profile '%s' started", profile_name)
        return jsonify({
            'status': 'started',
            'message': f'Profile {profile_name} started successfully',
            'output': output,
        })
    else:
        return jsonify({
            'error': f'Failed to start profile {profile_name}',
            'output': output,
        }), 500


@profiles_bp.route('/api/stop-profile/<profile_name>', methods=['POST'])
@validate_profile_name
def stop_profile(profile_name):
    """Stop and remove a profile container directly using docker commands."""
    container_name = f'{get_container_prefix()}-{profile_name}'

    try:
        container = docker_client.containers.get(container_name)
        container.stop(timeout=10)
        container.remove()
        logger.info("Profile '%s' stopped and removed", profile_name)
        return jsonify({
            'status': 'stopped',
            'message': f'Profile {profile_name} stopped and removed successfully',
        })
    except docker.errors.NotFound:
        return jsonify({
            'status': 'stopped',
            'message': f'Container {container_name} not found (already removed)',
        })
    except docker.errors.APIError as exc:
        logger.error("Failed to stop profile '%s': %s", profile_name, exc)
        return jsonify({
            'error': f'Failed to stop profile {profile_name}',
            'details': str(exc),
        }), 500


@profiles_bp.route('/api/recreate-profile/<profile_name>', methods=['POST'])
@validate_profile_name
def recreate_profile(profile_name):
    """Stop, remove and recreate a profile container to apply new config."""
    container_name = f'{get_container_prefix()}-{profile_name}'
    compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')

    if not os.path.exists(compose_file):
        return jsonify({'error': f'docker-compose.{profile_name}.yml not found'}), 404

    try:
        # Stop and remove existing container
        try:
            container = docker_client.containers.get(container_name)
            container.stop(timeout=10)
            container.remove()
        except docker.errors.NotFound:
            pass

        # Recreate with compose
        ok, output = compose_up(compose_file)
        if ok:
            logger.info("Profile '%s' recreated", profile_name)
            return jsonify({
                'status': 'recreated',
                'message': f'Profile {profile_name} recreated with new configuration',
                'output': output,
            })
        else:
            return jsonify({
                'error': f'Failed to recreate profile {profile_name}',
                'output': output,
            }), 500

    except docker.errors.APIError as exc:
        logger.error("Failed to recreate profile '%s': %s", profile_name, exc)
        return jsonify({
            'error': f'Failed to recreate profile {profile_name}',
            'details': str(exc),
        }), 500


@profiles_bp.route('/api/create-new-profile', methods=['POST'])
def create_new_profile():
    """Create a new profile directory with custom name."""
    data = request.get_json()
    display_name = data.get('name', '').strip()

    if not display_name:
        return jsonify({'error': 'Profile name is required'}), 400

    profile_name = sanitize_profile_name(display_name)
    profile_dir = os.path.join(config.PROFILES_DIR, profile_name)
    photos_dir = os.path.join(config.PHOTOS_DIR, profile_name)

    if os.path.exists(profile_dir):
        return jsonify({'error': f'Profile "{profile_name}" already exists'}), 400

    try:
        puid = config.DEFAULT_PUID
        pgid = config.DEFAULT_PGID

        os.makedirs(config.PROFILES_DIR, exist_ok=True)
        os.makedirs(config.PHOTOS_DIR, exist_ok=True)

        os.makedirs(profile_dir, exist_ok=True)
        os.chown(profile_dir, puid, pgid)

        os.makedirs(photos_dir, exist_ok=True)
        os.chown(photos_dir, puid, pgid)

        metadata = {
            'name': profile_name,
            'display_name': display_name,
            'created_at': datetime.now().isoformat(),
        }

        metadata_file = os.path.join(profile_dir, '.profile_metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        os.chown(metadata_file, puid, pgid)

        logger.info("Profile '%s' created (display: '%s')", profile_name, display_name)
        return jsonify({
            'status': 'created',
            'profile_name': profile_name,
            'display_name': display_name,
            'profile_dir': profile_dir,
            'photos_dir': photos_dir,
            'message': f'Profile "{display_name}" created as {profile_name}',
        })

    except OSError as exc:
        logger.error("Failed to create profile '%s': %s", profile_name, exc)
        return jsonify({'error': str(exc)}), 500


@profiles_bp.route('/api/delete-profile/<profile_name>', methods=['DELETE'])
@validate_profile_name
def delete_profile(profile_name):
    """Delete a profile: stop and remove container, delete docker-compose file."""
    prefix = get_container_prefix()
    container_name = f'{prefix}-{profile_name}'
    compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')

    errors = []
    success_messages = []

    try:
        # Step 1: Remove container
        try:
            container = docker_client.containers.get(container_name)
            try:
                container.stop(timeout=10)
                success_messages.append(f'Container {container_name} stopped')
            except docker.errors.APIError:
                success_messages.append('Container stop attempted (may already be stopped)')
            container.remove(force=True)
            success_messages.append(f'Container {container_name} removed')
        except docker.errors.NotFound:
            success_messages.append(f'Container {container_name} not found (already deleted)')
        except docker.errors.APIError as exc:
            errors.append(f'Error removing container: {str(exc)}')

        # Step 2: Delete compose file
        if os.path.exists(compose_file):
            try:
                os.remove(compose_file)
                success_messages.append(f'File docker-compose.{profile_name}.yml deleted')
            except OSError as exc:
                errors.append(f'Error deleting compose file: {str(exc)}')
        else:
            success_messages.append('Compose file not found (already deleted)')

        if errors:
            return jsonify({
                'status': 'partial',
                'message': 'Profile partially deleted with some errors',
                'success': success_messages,
                'errors': errors,
            }), 207
        else:
            logger.info("Profile '%s' deleted", profile_name)
            return jsonify({
                'status': 'deleted',
                'message': f'Profile {profile_name} deleted successfully',
                'success': success_messages,
            })

    except docker.errors.APIError as exc:
        logger.error("Error deleting profile '%s': %s", profile_name, exc)
        return jsonify({
            'status': 'error',
            'error': str(exc),
            'success': success_messages,
            'errors': errors,
        }), 500


@profiles_bp.route('/api/delete-profile-files/<profile_name>', methods=['DELETE'])
@validate_profile_name
def delete_profile_files(profile_name):
    """Delete only profile files without touching containers."""
    compose_file = os.path.join(config.WORKSPACE_PATH, f'docker-compose.{profile_name}.yml')
    profile_dir = os.path.join(config.PROFILES_DIR, profile_name)

    errors = []
    success_messages = []

    try:
        if os.path.exists(compose_file):
            try:
                os.remove(compose_file)
                success_messages.append(f'File docker-compose.{profile_name}.yml deleted')
            except OSError as exc:
                errors.append(f'Error deleting compose file: {str(exc)}')
        else:
            success_messages.append('Compose file not found')

        if os.path.exists(profile_dir):
            try:
                shutil.rmtree(profile_dir)
                success_messages.append(f'Profile directory {profile_name} deleted')
            except OSError as exc:
                errors.append(f'Error deleting profile directory: {str(exc)}')
        else:
            success_messages.append('Profile directory not found')

        if errors:
            return jsonify({
                'status': 'partial',
                'message': 'Profile files partially deleted with some errors',
                'success': success_messages,
                'errors': errors,
            }), 207
        else:
            logger.info("Profile files for '%s' deleted", profile_name)
            return jsonify({
                'status': 'deleted',
                'message': f'Profile {profile_name} files deleted successfully',
                'success': success_messages,
            })

    except OSError as exc:
        logger.error("Error deleting profile files for '%s': %s", profile_name, exc)
        return jsonify({
            'status': 'error',
            'error': str(exc),
            'success': success_messages,
            'errors': errors,
        }), 500


@profiles_bp.route('/api/browse-directories', methods=['POST'])
def browse_directories():
    """Browse directories on the host system."""
    data = request.get_json() or {}
    requested_path = data.get('path', '/')

    try:
        if requested_path.startswith('/host'):
            container_path = requested_path
        else:
            container_path = os.path.join('/host', requested_path.lstrip('/'))

        container_path = os.path.abspath(container_path)

        if not os.path.exists(container_path):
            return jsonify({'error': 'Path does not exist'}), 404

        if not os.path.isdir(container_path):
            return jsonify({'error': 'Path is not a directory'}), 400

        directories = []
        files_count = 0

        try:
            entries = os.listdir(container_path)
            for entry in sorted(entries):
                entry_container_path = os.path.join(container_path, entry)
                try:
                    if os.path.isdir(entry_container_path):
                        os.listdir(entry_container_path)
                        entry_user_path = entry_container_path.replace('/host', '', 1) or '/'
                        directories.append({
                            'name': entry,
                            'path': entry_user_path,
                        })
                    else:
                        files_count += 1
                except PermissionError:
                    entry_user_path = entry_container_path.replace('/host', '', 1) or '/'
                    directories.append({
                        'name': entry,
                        'path': entry_user_path,
                        'unreadable': True,
                    })
        except PermissionError:
            return jsonify({'error': 'Permission denied'}), 403

        parent_container_path = os.path.dirname(container_path)
        parent_user_path = parent_container_path.replace('/host', '', 1) or '/'
        parent_path = parent_user_path if parent_user_path != container_path.replace('/host', '', 1) else None

        current_user_path = container_path.replace('/host', '', 1) or '/'

        return jsonify({
            'current_path': current_user_path,
            'parent_path': parent_path,
            'directories': directories,
            'files_count': files_count,
        })

    except OSError as exc:
        logger.error("Error browsing directory '%s': %s", requested_path, exc)
        return jsonify({'error': str(exc)}), 500

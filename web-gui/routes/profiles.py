#!/usr/bin/env python3
import os
import json
import subprocess
import docker
import glob
import shutil
from datetime import datetime
from flask import Blueprint, jsonify, request
from utils.docker_client import docker_client
from utils.container_helpers import get_sync_containers, get_container_prefix
from utils.profile_helpers import get_profile_metadata, sanitize_profile_name
from utils.path_helpers import get_host_workspace_path

profiles_bp = Blueprint('profiles', __name__)


@profiles_bp.route('/api/available-profiles')
def api_available_profiles():
    """Get profiles that exist but don't have running containers"""
    # Find all profile directories in /workspace/profiles/
    profile_dirs = glob.glob('/workspace/profiles/*')
    available_profiles = []

    # Get running container names
    containers = get_sync_containers()
    running_profiles = set()
    for c in containers:
        # Extract profile name from container name (e.g., "gphotos-sync-family" -> "family")
        profile_name = c.name.replace(get_container_prefix() + '-', '', 1)
        running_profiles.add(profile_name)

    # Check each profile directory
    for profile_path in profile_dirs:
        profile_name = os.path.basename(profile_path)

        # Skip if already running
        if profile_name in running_profiles:
            continue

        compose_file = f'/workspace/docker-compose.{profile_name}.yml'
        has_compose = os.path.exists(compose_file)

        # Get metadata for display name
        metadata = get_profile_metadata(profile_name)
        display_name = metadata.get('display_name', profile_name)

        # Show all profiles that exist but aren't running
        available_profiles.append({
            'name': profile_name,
            'display_name': display_name,
            'path': profile_path,
            'has_compose': has_compose,
            'compose_file': f'docker-compose.{profile_name}.yml'
        })

    return jsonify(sorted(available_profiles, key=lambda x: x['display_name']))


@profiles_bp.route('/api/create-compose/<profile_name>', methods=['POST'])
def create_compose(profile_name):
    """Create docker-compose file for a profile with custom configuration"""
    # Get configuration from request body
    config = request.get_json() or {}

    # Use absolute host paths to avoid Docker volume issues
    workspace_path = get_host_workspace_path()

    # Extract configuration with defaults
    enable_cron = config.get('enable_cron', True)
    cron_schedule = config.get('cron_schedule', '0 3 * * *')
    run_on_startup = config.get('run_on_startup', True)
    loglevel = config.get('loglevel', 'info')
    worker_count = config.get('worker_count', 6)
    albums = config.get('albums', '')
    timezone = config.get('timezone', 'Europe/Rome')
    puid = config.get('puid', 1000)
    pgid = config.get('pgid', 1000)
    photo_dir = config.get('photo_dir', '')

    # Advanced options
    restart_schedule = config.get('restart_schedule', '')
    healthcheck_url = config.get('healthcheck_url', '')

    # Build environment section
    env_vars = [
        f'      - PUID={puid}',
        f'      - PGID={pgid}',
        f'      - LOGLEVEL={loglevel}',
        f'      - TZ={timezone}',
        f'      - WORKER_COUNT={worker_count}'
    ]

    # Only add cron-related env vars if cron is enabled
    if enable_cron:
        env_vars.insert(2, f'      - CRON_SCHEDULE={cron_schedule}')
        env_vars.insert(3, f'      - RUN_ON_STARTUP={str(run_on_startup).lower()}')

    # Add ALBUMS env var if specified
    if albums and albums.strip() and albums.strip().upper() != 'ALL':
        env_vars.append(f'      - ALBUMS={albums.strip()}')

    # Add restart schedule if specified
    if restart_schedule and restart_schedule.strip():
        env_vars.append(f'      - RESTART_SCHEDULE={restart_schedule.strip()}')

    # Add healthcheck if specified
    if healthcheck_url and healthcheck_url.strip():
        # Extract host and ID from full URL (e.g., https://hc-ping.com/abc-123)
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

    # Build command line if cron is disabled
    command_line = "    command: no-cron\n" if not enable_cron else ""

    # Determine photo directory (custom or default)
    if photo_dir and photo_dir.strip():
        # Use custom directory (user-provided absolute path)
        download_dir = photo_dir.strip()
    else:
        # Use default directory
        download_dir = f'{workspace_path}/photos/{profile_name}'

    # Use restart: "no" for no-cron mode, otherwise unless-stopped
    restart_policy = '"no"' if not enable_cron else "unless-stopped"

    compose_content = f"""services:
  gphotos-sync-{profile_name}:
    image: gphotos-sync:latest
    container_name: gphotos-sync-{profile_name}
{command_line}    restart: {restart_policy}
    privileged: true
    volumes:
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

    compose_file = f'/workspace/docker-compose.{profile_name}.yml'

    try:
        with open(compose_file, 'w') as f:
            f.write(compose_content)

        # Save photo_dir in profile metadata for later retrieval
        metadata_file = f'/workspace/profiles/{profile_name}/.profile_metadata.json'
        try:
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            else:
                metadata = {'name': profile_name, 'display_name': profile_name}

            # Update metadata with photo_dir
            metadata['photo_dir'] = photo_dir if photo_dir and photo_dir.strip() else ''

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as meta_error:
            # Don't fail if metadata update fails, just log it
            print(f"Warning: Could not update metadata: {meta_error}")

        return jsonify({
            'status': 'created',
            'file': f'docker-compose.{profile_name}.yml',
            'message': f'Docker compose file created for profile {profile_name}',
            'config': config
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@profiles_bp.route('/api/get-config/<profile_name>', methods=['GET'])
def get_config(profile_name):
    """Get current configuration from docker-compose file"""
    import yaml

    compose_file = f'/workspace/docker-compose.{profile_name}.yml'

    if not os.path.exists(compose_file):
        return jsonify({'error': 'Docker compose file not found'}), 404

    try:
        with open(compose_file, 'r') as f:
            compose_data = yaml.safe_load(f)

        # Extract environment variables and command
        service_name = f'gphotos-sync-{profile_name}'
        service_config = compose_data.get('services', {}).get(service_name, {})
        env_vars = service_config.get('environment', [])
        command = service_config.get('command', '')

        # Check if running in no-cron mode
        is_no_cron = command == 'no-cron'

        # Parse environment variables
        config = {
            'cron_schedule': 'disabled' if is_no_cron else '',
            'run_on_startup': True,
            'loglevel': 'info',
            'worker_count': 6,
            'albums': '',
            'timezone': 'Europe/Rome',
            'puid': 1000,
            'pgid': 1000,
            'restart_schedule': '',
            'healthcheck_url': ''
        }

        # Track healthcheck components
        healthcheck_host = ''
        healthcheck_id = ''

        for env in env_vars:
            if isinstance(env, str) and '=' in env:
                key, val = env.split('=', 1)
                key = key.strip()
                val = val.strip()

                if key == 'CRON_SCHEDULE':
                    config['cron_schedule'] = val
                elif key == 'RUN_ON_STARTUP':
                    config['run_on_startup'] = val.lower() == 'true'
                elif key == 'LOGLEVEL':
                    config['loglevel'] = val
                elif key == 'WORKER_COUNT':
                    config['worker_count'] = int(val)
                elif key == 'ALBUMS':
                    config['albums'] = val
                elif key == 'TZ':
                    config['timezone'] = val
                elif key == 'PUID':
                    config['puid'] = int(val)
                elif key == 'PGID':
                    config['pgid'] = int(val)
                elif key == 'RESTART_SCHEDULE':
                    config['restart_schedule'] = val
                elif key == 'HEALTHCHECK_HOST':
                    healthcheck_host = val
                elif key == 'HEALTHCHECK_ID':
                    healthcheck_id = val

        # Reconstruct full healthcheck URL if both parts are present
        if healthcheck_host and healthcheck_id:
            config['healthcheck_url'] = f"{healthcheck_host}/{healthcheck_id}"

        # Extract photo_dir from volumes
        volumes = service_config.get('volumes', [])
        config['photo_dir'] = ''
        for volume in volumes:
            if isinstance(volume, str) and ':/download' in volume:
                # Extract the host path (before the colon)
                host_path = volume.split(':')[0]
                # Check if it's a custom directory (not the default pattern)
                workspace_path = get_host_workspace_path()
                default_path = f'{workspace_path}/photos/{profile_name}'
                if host_path != default_path:
                    config['photo_dir'] = host_path
                break

        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@profiles_bp.route('/api/start-profile/<profile_name>', methods=['POST'])
def start_profile(profile_name):
    """Start a profile container using docker-compose"""
    compose_file = f'/workspace/docker-compose.{profile_name}.yml'

    if not os.path.exists(compose_file):
        return jsonify({'error': f'docker-compose.{profile_name}.yml not found'}), 404

    try:
        # Run docker compose up -d with --build to ensure it uses the latest base image
        result = subprocess.run(
            ['docker', 'compose', '-f', compose_file, 'up', '-d', '--build'],
            cwd='/workspace',
            capture_output=True,
            text=True,
            timeout=120  # Increased timeout for build
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'started',
                'message': f'Profile {profile_name} started successfully',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': f'Failed to start profile {profile_name}',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@profiles_bp.route('/api/stop-profile/<profile_name>', methods=['POST'])
def stop_profile(profile_name):
    """Stop and remove a profile container directly using docker commands"""
    container_name = f'gphotos-sync-{profile_name}'

    try:
        # Get the container
        container = docker_client.containers.get(container_name)

        # Stop the container
        container.stop(timeout=10)

        # Remove the container
        container.remove()

        return jsonify({
            'status': 'stopped',
            'message': f'Profile {profile_name} stopped and removed successfully'
        })

    except docker.errors.NotFound:
        return jsonify({
            'status': 'stopped',
            'message': f'Container {container_name} not found (already removed)'
        })
    except Exception as e:
        return jsonify({
            'error': f'Failed to stop profile {profile_name}',
            'details': str(e)
        }), 500


@profiles_bp.route('/api/recreate-profile/<profile_name>', methods=['POST'])
def recreate_profile(profile_name):
    """Stop, remove and recreate a profile container using docker-compose to apply new config"""
    container_name = f'gphotos-sync-{profile_name}'
    compose_file = f'/workspace/docker-compose.{profile_name}.yml'

    if not os.path.exists(compose_file):
        return jsonify({'error': f'docker-compose.{profile_name}.yml not found'}), 404

    try:
        # Step 1: Stop and remove the container using Docker API (doesn't affect other containers)
        try:
            container = docker_client.containers.get(container_name)
            container.stop(timeout=10)
            container.remove()
        except docker.errors.NotFound:
            pass  # Container already removed, that's fine

        # Step 2: Start the container using docker-compose (reads new config from yaml)
        result = subprocess.run(
            ['docker', 'compose', '-f', compose_file, 'up', '-d', '--build'],
            cwd='/workspace',
            capture_output=True,
            text=True,
            timeout=120  # Increased timeout for build
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'recreated',
                'message': f'Profile {profile_name} recreated with new configuration',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': f'Failed to recreate profile {profile_name}',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({
            'error': f'Failed to recreate profile {profile_name}',
            'details': str(e)
        }), 500


@profiles_bp.route('/api/create-new-profile', methods=['POST'])
def create_new_profile():
    """Create a new profile directory with custom name"""
    data = request.get_json()
    display_name = data.get('name', '').strip()

    if not display_name:
        return jsonify({'error': 'Profile name is required'}), 400

    # Sanitize the name for filesystem use
    profile_name = sanitize_profile_name(display_name)

    # Check if profile already exists
    profile_dir = f'/workspace/profiles/{profile_name}'
    photos_dir = f'/workspace/photos/{profile_name}'

    if os.path.exists(profile_dir):
        return jsonify({'error': f'Profile "{profile_name}" already exists'}), 400

    try:
        # Get PUID and PGID to create directories with correct ownership
        puid = int(os.getenv('PUID', '1000'))
        pgid = int(os.getenv('PGID', '1000'))

        # Create profiles base directory if needed
        os.makedirs('/workspace/profiles', exist_ok=True)
        os.makedirs('/workspace/photos', exist_ok=True)

        # Create profile directory
        os.makedirs(profile_dir, exist_ok=True)
        os.chown(profile_dir, puid, pgid)

        # Create photos directory
        os.makedirs(photos_dir, exist_ok=True)
        os.chown(photos_dir, puid, pgid)

        # Create a metadata file to store display name
        metadata = {
            'name': profile_name,
            'display_name': display_name,
            'created_at': datetime.now().isoformat()
        }

        metadata_file = f'{profile_dir}/.profile_metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        os.chown(metadata_file, puid, pgid)

        return jsonify({
            'status': 'created',
            'profile_name': profile_name,
            'display_name': display_name,
            'profile_dir': profile_dir,
            'photos_dir': photos_dir,
            'message': f'Profile "{display_name}" created as {profile_name}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@profiles_bp.route('/api/delete-profile/<profile_name>', methods=['DELETE'])
def delete_profile(profile_name):
    """Delete a profile: stop and remove container, delete docker-compose file"""
    container_name = f'{get_container_prefix()}-{profile_name}'
    compose_file = f'/workspace/docker-compose.{profile_name}.yml'

    errors = []
    success_messages = []

    try:
        # Step 1: Check if container exists and remove it
        try:
            container = docker_client.containers.get(container_name)
            # Always try to stop the container first, regardless of status
            try:
                container.stop(timeout=10)
                success_messages.append(f'Container {container_name} stopped')
            except Exception as stop_error:
                # Container might already be stopped, continue anyway
                success_messages.append(f'Container stop attempted (may already be stopped)')
            # Remove container (force=True to ensure removal even if stop failed)
            container.remove(force=True)
            success_messages.append(f'Container {container_name} removed')
        except docker.errors.NotFound:
            success_messages.append(f'Container {container_name} not found (already deleted)')
        except Exception as e:
            errors.append(f'Error removing container: {str(e)}')

        # Step 2: Delete docker-compose file if it exists
        if os.path.exists(compose_file):
            try:
                os.remove(compose_file)
                success_messages.append(f'File docker-compose.{profile_name}.yml deleted')
            except Exception as e:
                errors.append(f'Error deleting compose file: {str(e)}')
        else:
            success_messages.append(f'Compose file not found (already deleted)')

        # Return response
        if errors:
            return jsonify({
                'status': 'partial',
                'message': 'Profile partially deleted with some errors',
                'success': success_messages,
                'errors': errors
            }), 207  # Multi-Status
        else:
            return jsonify({
                'status': 'deleted',
                'message': f'Profile {profile_name} deleted successfully',
                'success': success_messages
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'success': success_messages,
            'errors': errors
        }), 500


@profiles_bp.route('/api/delete-profile-files/<profile_name>', methods=['DELETE'])
def delete_profile_files(profile_name):
    """Delete only profile files (docker-compose, metadata, profile directory) without touching containers"""
    compose_file = f'/workspace/docker-compose.{profile_name}.yml'
    profile_dir = f'/workspace/profiles/{profile_name}'

    errors = []
    success_messages = []

    try:
        # Step 1: Delete docker-compose file if it exists
        if os.path.exists(compose_file):
            try:
                os.remove(compose_file)
                success_messages.append(f'File docker-compose.{profile_name}.yml deleted')
            except Exception as e:
                errors.append(f'Error deleting compose file: {str(e)}')
        else:
            success_messages.append(f'Compose file not found')

        # Step 2: Delete profile directory if it exists
        if os.path.exists(profile_dir):
            try:
                shutil.rmtree(profile_dir)
                success_messages.append(f'Profile directory {profile_name} deleted')
            except Exception as e:
                errors.append(f'Error deleting profile directory: {str(e)}')
        else:
            success_messages.append(f'Profile directory not found')

        # Return response
        if errors:
            return jsonify({
                'status': 'partial',
                'message': 'Profile files partially deleted with some errors',
                'success': success_messages,
                'errors': errors
            }), 207  # Multi-Status
        else:
            return jsonify({
                'status': 'deleted',
                'message': f'Profile {profile_name} files deleted successfully',
                'success': success_messages
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'success': success_messages,
            'errors': errors
        }), 500


@profiles_bp.route('/api/browse-directories', methods=['POST'])
def browse_directories():
    """Browse directories on the host system"""
    data = request.get_json() or {}
    requested_path = data.get('path', '/')

    try:
        # Map the requested path to the host mount point
        # The host filesystem is mounted at /host in the container
        if requested_path.startswith('/host'):
            # Already using host prefix
            container_path = requested_path
        else:
            # Convert user path to container path
            # User sees: /home/user/photos
            # Container needs: /host/home/user/photos
            container_path = os.path.join('/host', requested_path.lstrip('/'))

        # Resolve to absolute path
        container_path = os.path.abspath(container_path)

        # Security check: ensure path exists and is a directory
        if not os.path.exists(container_path):
            return jsonify({'error': 'Path does not exist'}), 404

        if not os.path.isdir(container_path):
            return jsonify({'error': 'Path is not a directory'}), 400

        # List directories
        directories = []
        files_count = 0

        try:
            entries = os.listdir(container_path)
            for entry in sorted(entries):
                entry_container_path = os.path.join(container_path, entry)
                try:
                    if os.path.isdir(entry_container_path):
                        # Check if readable
                        os.listdir(entry_container_path)

                        # Convert back to user-facing path (remove /host prefix)
                        entry_user_path = entry_container_path.replace('/host', '', 1) or '/'

                        directories.append({
                            'name': entry,
                            'path': entry_user_path
                        })
                    else:
                        files_count += 1
                except PermissionError:
                    # Skip directories we can't read
                    entry_user_path = entry_container_path.replace('/host', '', 1) or '/'
                    directories.append({
                        'name': entry,
                        'path': entry_user_path,
                        'unreadable': True
                    })
        except PermissionError:
            return jsonify({'error': 'Permission denied'}), 403

        # Get parent directory
        parent_container_path = os.path.dirname(container_path)
        parent_user_path = parent_container_path.replace('/host', '', 1) or '/'
        parent_path = parent_user_path if parent_user_path != container_path.replace('/host', '', 1) else None

        # Convert current path back to user-facing format
        current_user_path = container_path.replace('/host', '', 1) or '/'

        return jsonify({
            'current_path': current_user_path,
            'parent_path': parent_path,
            'directories': directories,
            'files_count': files_count
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

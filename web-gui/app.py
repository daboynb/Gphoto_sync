#!/usr/bin/env python3
import os
import json
import docker
from flask import Flask, render_template, jsonify, Response, stream_with_context
from datetime import datetime, timedelta
from croniter import croniter
import pytz

app = Flask(__name__)

# Initialize Docker client with explicit socket path
try:
    docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')
except Exception as e:
    print(f"Error connecting to Docker: {e}")
    docker_client = None

def get_container_prefix():
    """Get the container name prefix from environment or default"""
    return os.getenv('CONTAINER_PREFIX', 'gphotos-sync')

def get_sync_containers():
    """Get all gphotos-sync containers"""
    prefix = get_container_prefix()
    containers = docker_client.containers.list(all=True, filters={'name': prefix})
    return containers

def parse_cron_next_run(cron_schedule, tz='Europe/Rome'):
    """Calculate next run time from cron schedule"""
    try:
        # Get timezone-aware current time
        timezone = pytz.timezone(tz)
        base_time = datetime.now(timezone)

        # Calculate next cron run
        cron = croniter(cron_schedule, base_time)
        next_run = cron.get_next(datetime)

        # Calculate time difference
        time_until = next_run - base_time

        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)

        return {
            'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S'),
            'time_until': f"{hours}h {minutes}m"
        }
    except Exception as e:
        return {'next_run': 'N/A', 'time_until': 'N/A'}

def sanitize_profile_name(name):
    """Convert profile name to filesystem-safe format"""
    # Convert to lowercase, replace spaces/special chars with underscore
    import re
    sanitized = re.sub(r'[^a-z0-9_-]', '_', name.lower().strip())
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized if sanitized else 'profile'

def get_profile_metadata(profile_name):
    """Get profile metadata from metadata file"""
    metadata_file = f'/workspace/profiles/{profile_name}/.profile_metadata.json'
    try:
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'name': profile_name, 'display_name': profile_name}

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

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/api/containers')
def api_containers():
    """Get all container info"""
    containers = get_sync_containers()
    return jsonify([get_container_info(c) for c in containers])

@app.route('/api/container/<container_id>/logs')
def api_logs(container_id):
    """Get container logs (last 30 lines)"""
    try:
        container = docker_client.containers.get(container_id)
        logs = container.logs(tail=30, timestamps=True).decode('utf-8')
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/container/<container_id>/logs/stream')
def stream_logs(container_id):
    """Stream container logs in real-time"""
    def generate():
        try:
            container = docker_client.containers.get(container_id)
            for log in container.logs(stream=True, follow=True, timestamps=True):
                yield f"data: {log.decode('utf-8')}\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/container/<container_id>/start', methods=['POST'])
def start_container(container_id):
    """Start a container"""
    try:
        container = docker_client.containers.get(container_id)
        container.start()
        return jsonify({'status': 'started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/container/<container_id>/stop', methods=['POST'])
def stop_container(container_id):
    """Stop a container"""
    try:
        container = docker_client.containers.get(container_id)
        container.stop()
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/container/<container_id>/restart', methods=['POST'])
def restart_container(container_id):
    """Restart a container"""
    try:
        container = docker_client.containers.get(container_id)
        container.restart()
        return jsonify({'status': 'restarted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rebuild-image/stream', methods=['GET'])
def rebuild_image_stream():
    """Stream rebuild progress in real-time using Server-Sent Events"""
    import subprocess
    import time

    def generate():
        try:
            # Send initial status
            msg = json.dumps({'type': 'status', 'message': 'Starting Docker image rebuild...'})
            yield f"data: {msg}\n\n"
            time.sleep(0.5)

            # Step 0: Remove ALL related images to force complete rebuild
            msg = json.dumps({'type': 'status', 'message': 'Removing old images...'})
            yield f"data: {msg}\n\n"
            msg = json.dumps({'type': 'log', 'message': '=== Cleaning Old Images ===\n'})
            yield f"data: {msg}\n\n"

            # Remove gphotos-sync images
            prune_process = subprocess.Popen(
                ['docker', 'images', '--format', '{{.Repository}}:{{.Tag}}', '--filter', 'reference=*gphotos-sync*'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            images_to_remove = []
            for line in iter(prune_process.stdout.readline, ''):
                if line.strip():
                    images_to_remove.append(line.strip())
            prune_process.wait()

            # Remove each image
            for img in images_to_remove:
                msg = json.dumps({'type': 'log', 'message': f'Removing image: {img}\n'})
                yield f"data: {msg}\n\n"
                subprocess.run(['docker', 'rmi', '-f', img], capture_output=True)

            msg = json.dumps({'type': 'log', 'message': f'Removed {len(images_to_remove)} old images\n\n'})
            yield f"data: {msg}\n\n"

            # Remove dangling images (untagged images that may be cached)
            msg = json.dumps({'type': 'log', 'message': 'Removing dangling images...\n'})
            yield f"data: {msg}\n\n"

            try:
                prune_result = docker_client.images.prune(filters={'dangling': True})
                msg = json.dumps({'type': 'log', 'message': f'Removed {len(prune_result.get("ImagesDeleted", []))} dangling images\n\n'})
                yield f"data: {msg}\n\n"
            except Exception as e:
                msg = json.dumps({'type': 'log', 'message': f'Warning: could not prune dangling images: {str(e)}\n\n'})
                yield f"data: {msg}\n\n"

            # Step 1: Build the new Docker image with streaming output
            msg = json.dumps({'type': 'status', 'message': 'Building Docker image (this may take a few minutes)...'})
            yield f"data: {msg}\n\n"
            msg = json.dumps({'type': 'log', 'message': '=== Building Docker Image ===\n'})
            yield f"data: {msg}\n\n"

            build_process = subprocess.Popen(
                ['docker', 'build', '--no-cache', '-t', 'gphotos-sync:latest', '.'],
                cwd='/workspace',
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Stream build output line by line
            for line in iter(build_process.stdout.readline, ''):
                if line:
                    msg = json.dumps({'type': 'log', 'message': line})
                    yield f"data: {msg}\n\n"

            build_process.wait()

            if build_process.returncode != 0:
                msg = json.dumps({'type': 'error', 'message': 'Docker build failed!'})
                yield f"data: {msg}\n\n"
                return

            msg = json.dumps({'type': 'log', 'message': '\n✓ Docker image built successfully!\n\n'})
            yield f"data: {msg}\n\n"

            # Step 2: Get ALL containers (running or stopped)
            msg = json.dumps({'type': 'status', 'message': 'Checking containers...'})
            yield f"data: {msg}\n\n"

            containers = get_sync_containers()
            all_profiles = []

            for container in containers:
                profile_name = container.name.replace(get_container_prefix() + '-', '', 1)
                all_profiles.append(profile_name)

            if not all_profiles:
                msg = json.dumps({'type': 'log', 'message': 'No containers found to recreate.\n'})
                yield f"data: {msg}\n\n"
                msg = json.dumps({'type': 'complete', 'message': 'Rebuild completed successfully!', 'restarted_count': 0})
                yield f"data: {msg}\n\n"
                return

            msg = json.dumps({'type': 'log', 'message': f'Found {len(all_profiles)} containers to recreate.\n\n'})
            yield f"data: {msg}\n\n"

            # Step 3: Recreate ALL containers with new image
            msg = json.dumps({'type': 'status', 'message': f'Recreating {len(all_profiles)} containers...'})
            yield f"data: {msg}\n\n"
            msg = json.dumps({'type': 'log', 'message': '=== Recreating Containers ===\n'})
            yield f"data: {msg}\n\n"

            restart_errors = []
            for i, profile_name in enumerate(all_profiles, 1):
                compose_file = f'/workspace/docker-compose.{profile_name}.yml'

                msg = json.dumps({'type': 'log', 'message': f'[{i}/{len(all_profiles)}] Recreating {profile_name}...\n'})
                yield f"data: {msg}\n\n"

                if not os.path.exists(compose_file):
                    error_msg = f'  ✗ Compose file not found for {profile_name}\n'
                    restart_errors.append(error_msg)
                    msg = json.dumps({'type': 'log', 'message': error_msg})
                    yield f"data: {msg}\n\n"
                    continue

                # First: Stop and remove the old container
                msg = json.dumps({'type': 'log', 'message': f'  Stopping old container...\n'})
                yield f"data: {msg}\n\n"

                # Stop and remove container
                try:
                    container = docker_client.containers.get(f'gphotos-sync-{profile_name}')
                    container.stop(timeout=10)
                    container.remove()
                    msg = json.dumps({'type': 'log', 'message': f'    Container stopped and removed\n'})
                    yield f"data: {msg}\n\n"
                except docker.errors.NotFound:
                    msg = json.dumps({'type': 'log', 'message': f'    Container not found (already removed)\n'})
                    yield f"data: {msg}\n\n"

                # Remove any cached images for this service
                msg = json.dumps({'type': 'log', 'message': f'  Removing cached images...\n'})
                yield f"data: {msg}\n\n"

                # Get all images related to this profile
                all_images = docker_client.images.list()
                for img in all_images:
                    for tag in img.tags:
                        # Remove images that match this profile or any docker-compose generated ones
                        if profile_name in tag.lower() and 'gphotos-sync' in tag.lower():
                            try:
                                docker_client.images.remove(tag, force=True)
                                msg = json.dumps({'type': 'log', 'message': f'    Removed image: {tag}\n'})
                                yield f"data: {msg}\n\n"
                            except:
                                pass

                # Second: Start with fresh image from gphotos-sync:latest
                msg = json.dumps({'type': 'log', 'message': f'  Creating container with fresh image...\n'})
                yield f"data: {msg}\n\n"

                recreate_process = subprocess.Popen(
                    ['docker', 'compose', '-f', compose_file, 'up', '-d', '--pull', 'never'],
                    cwd='/workspace',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )

                # Stream recreate output
                for line in iter(recreate_process.stdout.readline, ''):
                    if line:
                        msg = json.dumps({'type': 'log', 'message': '  ' + line})
                        yield f"data: {msg}\n\n"

                recreate_process.wait()

                if recreate_process.returncode != 0:
                    error_msg = f'  ✗ Failed to restart {profile_name}\n'
                    restart_errors.append(error_msg)
                    msg = json.dumps({'type': 'log', 'message': error_msg})
                    yield f"data: {msg}\n\n"
                else:
                    msg = json.dumps({'type': 'log', 'message': f'  ✓ {profile_name} restarted successfully\n'})
                    yield f"data: {msg}\n\n"

            # Final status
            if restart_errors:
                msg = json.dumps({'type': 'warning', 'message': f'Rebuild completed with {len(restart_errors)} errors'})
                yield f"data: {msg}\n\n"
            else:
                msg = json.dumps({'type': 'log', 'message': f'\n✓ All {len(all_profiles)} containers recreated successfully!\n'})
                yield f"data: {msg}\n\n"

            msg = json.dumps({'type': 'complete', 'message': 'Rebuild completed!', 'restarted_count': len(all_profiles), 'error_count': len(restart_errors)})
            yield f"data: {msg}\n\n"

        except Exception as e:
            msg = json.dumps({'type': 'error', 'message': f'Error: {str(e)}'})
            yield f"data: {msg}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/stats')
def api_stats():
    """Get overall stats"""
    containers = get_sync_containers()
    total = len(containers)
    running = sum(1 for c in containers if c.status == 'running')
    stopped = total - running

    return jsonify({
        'total': total,
        'running': running,
        'stopped': stopped
    })

@app.route('/api/available-profiles')
def api_available_profiles():
    """Get profiles that exist but don't have running containers"""
    import os
    import glob

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

@app.route('/api/create-compose/<profile_name>', methods=['POST'])
def create_compose(profile_name):
    """Create docker-compose file for a profile with custom configuration"""
    import os
    from flask import request

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

@app.route('/api/check-auth/<profile_name>', methods=['GET'])
def check_auth(profile_name):
    """Check if profile has authentication cookies"""
    cookies_file = f'/workspace/profiles/{profile_name}/Default/Cookies'
    has_cookies = os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0
    return jsonify({'authenticated': has_cookies})

@app.route('/api/get-config/<profile_name>', methods=['GET'])
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

@app.route('/api/start-profile/<profile_name>', methods=['POST'])
def start_profile(profile_name):
    """Start a profile container using docker-compose"""
    import subprocess

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

@app.route('/api/stop-profile/<profile_name>', methods=['POST'])
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

@app.route('/api/recreate-profile/<profile_name>', methods=['POST'])
def recreate_profile(profile_name):
    """Stop, remove and recreate a profile container using docker-compose to apply new config"""
    import subprocess

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

@app.route('/api/create-new-profile', methods=['POST'])
def create_new_profile():
    """Create a new profile directory with custom name"""
    import subprocess
    from flask import request

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

@app.route('/api/start-auth/<profile_name>', methods=['POST'])
def start_auth(profile_name):
    """Start VNC authentication container for a profile"""
    import subprocess

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

@app.route('/api/reauth-profile/<profile_name>', methods=['POST'])
def reauth_profile(profile_name):
    """Re-authenticate a running profile by loading it in VNC"""
    import subprocess

    container_name = f'gphotos-sync-{profile_name}'

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

@app.route('/api/stop-auth', methods=['POST'])
def stop_auth():
    """Stop VNC authentication container"""
    import subprocess

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

@app.route('/api/auth-status', methods=['GET'])
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

@app.route('/api/delete-profile/<profile_name>', methods=['DELETE'])
def delete_profile(profile_name):
    """Delete a profile: stop and remove container, delete docker-compose file"""
    import subprocess

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

@app.route('/api/delete-profile-files/<profile_name>', methods=['DELETE'])
def delete_profile_files(profile_name):
    """Delete only profile files (docker-compose, metadata, profile directory) without touching containers"""
    import shutil

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

@app.route('/api/browse-directories', methods=['POST'])
def browse_directories():
    """Browse directories on the host system"""
    from flask import request

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

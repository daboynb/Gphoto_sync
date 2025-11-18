#!/usr/bin/env python3
import os
import json
import docker
from flask import Flask, render_template, jsonify, Response, stream_with_context
from datetime import datetime, timedelta
from croniter import croniter

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
        base_time = datetime.now()
        cron = croniter(cron_schedule, base_time)
        next_run = cron.get_next(datetime)
        time_until = next_run - base_time

        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)

        return {
            'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S'),
            'time_until': f"{hours}h {minutes}m"
        }
    except:
        return {'next_run': 'N/A', 'time_until': 'N/A'}

def get_profile_metadata(profile_num):
    """Get custom profile name from metadata file"""
    metadata_file = f'/workspace/profile{profile_num}/.profile_metadata.json'
    try:
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                return metadata.get('name', f'profile{profile_num}')
    except:
        pass
    return f'profile{profile_num}'

def get_container_info(container):
    """Extract relevant info from container"""
    env_vars = {}
    if container.attrs.get('Config', {}).get('Env'):
        for env in container.attrs['Config']['Env']:
            if '=' in env:
                key, val = env.split('=', 1)
                env_vars[key] = val

    cron_info = parse_cron_next_run(env_vars.get('CRON_SCHEDULE', '0 2 * * *'))

    profile_name = container.name.replace(get_container_prefix(), '').replace('-', '').strip()
    if not profile_name:
        profile_name = 'default'

    # Get custom profile name if available
    profile_num = profile_name.replace('profile', '')
    display_name = profile_name
    if profile_num.isdigit():
        custom_name = get_profile_metadata(int(profile_num))
        display_name = custom_name

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
        'time_until': cron_info['time_until']
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
    """Get container logs"""
    try:
        container = docker_client.containers.get(container_id)
        logs = container.logs(tail=500, timestamps=True).decode('utf-8')
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

    # Find all profile directories
    profile_dirs = glob.glob('/workspace/profile*')
    available_profiles = []

    # Get running container names
    containers = get_sync_containers()
    running_profiles = set()
    for c in containers:
        # Extract profile number from container name
        name = c.name.replace(get_container_prefix(), '').replace('-', '')
        if name.startswith('profile'):
            running_profiles.add(name)

    # Check each profile directory
    for profile_path in profile_dirs:
        profile_name = os.path.basename(profile_path)

        # Skip if already running
        if profile_name in running_profiles:
            continue

        # Extract profile number
        profile_num = profile_name.replace('profile', '')
        if profile_num.isdigit():
            compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'
            has_compose = os.path.exists(compose_file)

            # Get custom display name
            display_name = get_profile_metadata(int(profile_num))

            # Show all profiles that exist but aren't running
            # The UI will offer to create docker-compose if missing
            available_profiles.append({
                'name': profile_name,
                'display_name': display_name,
                'number': int(profile_num),
                'path': profile_path,
                'has_compose': has_compose,
                'compose_file': f'docker-compose.profile{profile_num}.yml'
            })

    return jsonify(sorted(available_profiles, key=lambda x: x['number']))

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

@app.route('/api/create-compose/<int:profile_num>', methods=['POST'])
def create_compose(profile_num):
    """Create docker-compose file for a profile with custom configuration"""
    import os
    from flask import request

    # Get configuration from request body
    config = request.get_json() or {}

    # Use absolute host paths to avoid Docker volume issues
    workspace_path = get_host_workspace_path()

    # Extract configuration with defaults
    cron_schedule = config.get('cron_schedule', f'0 {2 + profile_num} * * *')
    run_on_startup = config.get('run_on_startup', True)
    loglevel = config.get('loglevel', 'info')
    worker_count = config.get('worker_count', 6)
    albums = config.get('albums', '')
    timezone = config.get('timezone', 'Europe/Rome')
    puid = config.get('puid', 1000)
    pgid = config.get('pgid', 1000)

    # Build environment section
    env_vars = [
        f'      - PUID={puid}',
        f'      - PGID={pgid}',
        f'      - CRON_SCHEDULE={cron_schedule}',
        f'      - RUN_ON_STARTUP={str(run_on_startup).lower()}',
        f'      - LOGLEVEL={loglevel}',
        f'      - TZ={timezone}',
        f'      - WORKER_COUNT={worker_count}'
    ]

    # Add ALBUMS env var if specified
    if albums and albums.strip() and albums.strip().upper() != 'ALL':
        env_vars.append(f'      - ALBUMS={albums.strip()}')

    compose_content = f"""services:
  gphotos-sync-profile{profile_num}:
    image: gphotos-sync:latest
    container_name: gphotos-sync-profile{profile_num}
    restart: unless-stopped
    privileged: true
    volumes:
      - {workspace_path}/profile{profile_num}:/tmp/gphotos-cdp
      - {workspace_path}/photos{profile_num}:/download
    environment:
{chr(10).join(env_vars)}
    networks:
      - gphotos-network

networks:
  gphotos-network:
    external: true
"""

    compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'

    try:
        with open(compose_file, 'w') as f:
            f.write(compose_content)

        return jsonify({
            'status': 'created',
            'file': f'docker-compose.profile{profile_num}.yml',
            'message': f'Docker compose file created for profile {profile_num}',
            'config': config
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get-config/<int:profile_num>', methods=['GET'])
def get_config(profile_num):
    """Get current configuration from docker-compose file"""
    import yaml

    compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'

    if not os.path.exists(compose_file):
        return jsonify({'error': 'Docker compose file not found'}), 404

    try:
        with open(compose_file, 'r') as f:
            compose_data = yaml.safe_load(f)

        # Extract environment variables
        service_name = f'gphotos-sync-profile{profile_num}'
        env_vars = compose_data.get('services', {}).get(service_name, {}).get('environment', [])

        # Parse environment variables
        config = {
            'cron_schedule': '',
            'run_on_startup': True,
            'loglevel': 'info',
            'worker_count': 6,
            'albums': '',
            'timezone': 'Europe/Rome',
            'puid': 1000,
            'pgid': 1000
        }

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

        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-profile/<int:profile_num>', methods=['POST'])
def start_profile(profile_num):
    """Start a profile container using docker-compose"""
    import subprocess

    compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'

    if not os.path.exists(compose_file):
        return jsonify({'error': f'docker-compose.profile{profile_num}.yml not found'}), 404

    try:
        # Run docker compose up -d
        result = subprocess.run(
            ['docker', 'compose', '-f', compose_file, 'up', '-d'],
            cwd='/workspace',
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'started',
                'message': f'Profile {profile_num} started successfully',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': f'Failed to start profile {profile_num}',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stop-profile/<int:profile_num>', methods=['POST'])
def stop_profile(profile_num):
    """Stop and remove a profile container directly using docker commands"""
    container_name = f'gphotos-sync-profile{profile_num}'

    try:
        # Get the container
        container = docker_client.containers.get(container_name)

        # Stop the container
        container.stop(timeout=10)

        # Remove the container
        container.remove()

        return jsonify({
            'status': 'stopped',
            'message': f'Profile {profile_num} stopped and removed successfully'
        })

    except docker.errors.NotFound:
        return jsonify({
            'status': 'stopped',
            'message': f'Container {container_name} not found (already removed)'
        })
    except Exception as e:
        return jsonify({
            'error': f'Failed to stop profile {profile_num}',
            'details': str(e)
        }), 500

@app.route('/api/recreate-profile/<int:profile_num>', methods=['POST'])
def recreate_profile(profile_num):
    """Stop, remove and recreate a profile container using docker-compose to apply new config"""
    import subprocess

    container_name = f'gphotos-sync-profile{profile_num}'
    compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'

    if not os.path.exists(compose_file):
        return jsonify({'error': f'docker-compose.profile{profile_num}.yml not found'}), 404

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
            ['docker', 'compose', '-f', compose_file, 'up', '-d', '--no-recreate'],
            cwd='/workspace',
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return jsonify({
                'status': 'recreated',
                'message': f'Profile {profile_num} recreated with new configuration',
                'output': result.stdout
            })
        else:
            return jsonify({
                'error': f'Failed to recreate profile {profile_num}',
                'output': result.stderr
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out'}), 500
    except Exception as e:
        return jsonify({
            'error': f'Failed to recreate profile {profile_num}',
            'details': str(e)
        }), 500

@app.route('/api/create-new-profile', methods=['POST'])
def create_new_profile():
    """Create a new profile directory with custom name"""
    import subprocess
    from flask import request

    data = request.get_json()
    profile_name = data.get('name', '').strip()

    if not profile_name:
        return jsonify({'error': 'Profile name is required'}), 400

    # Find next available profile number
    profile_num = 1
    while os.path.exists(f'/workspace/profile{profile_num}'):
        profile_num += 1

    profile_dir = f'/workspace/profile{profile_num}'
    photos_dir = f'/workspace/photos{profile_num}'

    try:
        # Get PUID and PGID to create directories with correct ownership
        puid = int(os.getenv('PUID', '1000'))
        pgid = int(os.getenv('PGID', '1000'))

        # Create profile directory
        os.makedirs(profile_dir, exist_ok=True)
        os.chown(profile_dir, puid, pgid)

        # Create photos directory
        os.makedirs(photos_dir, exist_ok=True)
        os.chown(photos_dir, puid, pgid)

        # Create a metadata file to store custom name
        metadata = {
            'name': profile_name,
            'created_at': datetime.now().isoformat(),
            'profile_num': profile_num
        }

        metadata_file = f'{profile_dir}/.profile_metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        os.chown(metadata_file, puid, pgid)

        return jsonify({
            'status': 'created',
            'profile_num': profile_num,
            'profile_name': profile_name,
            'profile_dir': profile_dir,
            'photos_dir': photos_dir,
            'message': f'Profile "{profile_name}" created as profile{profile_num}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-auth/<int:profile_num>', methods=['POST'])
def start_auth(profile_num):
    """Start VNC authentication container for a profile"""
    import subprocess

    # Check if profile directory exists
    if not os.path.exists(f'/workspace/profile{profile_num}'):
        return jsonify({'error': f'Profile directory profile{profile_num} not found'}), 404

    try:
        # Get PUID and PGID from environment or use defaults
        puid = os.getenv('PUID', '1000')
        pgid = os.getenv('PGID', '1000')

        # Get the host path for the profile
        # Since we're running docker from inside web-gui container,
        # we need to use the host path, not the container path
        host_workspace = get_host_workspace_path()
        profile_dir = f'{host_workspace}/profile{profile_num}'

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
                'profile_num': profile_num,
                'vnc_url': 'http://localhost:6080',
                'message': f'VNC container started for profile{profile_num}',
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

@app.route('/api/delete-profile/<int:profile_num>', methods=['DELETE'])
def delete_profile(profile_num):
    """Delete a profile: stop and remove container, delete docker-compose file"""
    import subprocess

    container_name = f'{get_container_prefix()}-profile{profile_num}'
    compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'

    errors = []
    success_messages = []

    try:
        # Step 1: Check if container exists and remove it
        try:
            container = docker_client.containers.get(container_name)
            # Stop container if running
            if container.status == 'running':
                container.stop(timeout=10)
                success_messages.append(f'Container {container_name} stopped')
            # Remove container
            container.remove()
            success_messages.append(f'Container {container_name} removed')
        except docker.errors.NotFound:
            success_messages.append(f'Container {container_name} not found (already deleted)')
        except Exception as e:
            errors.append(f'Error removing container: {str(e)}')

        # Step 2: Delete docker-compose file if it exists
        if os.path.exists(compose_file):
            try:
                os.remove(compose_file)
                success_messages.append(f'File docker-compose.profile{profile_num}.yml deleted')
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
                'message': f'Profile {profile_num} deleted successfully',
                'success': success_messages
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'success': success_messages,
            'errors': errors
        }), 500

@app.route('/api/delete-profile-files/<int:profile_num>', methods=['DELETE'])
def delete_profile_files(profile_num):
    """Delete only profile files (docker-compose, metadata, profile directory) without touching containers"""
    import shutil

    compose_file = f'/workspace/docker-compose.profile{profile_num}.yml'
    profile_dir = f'/workspace/profile{profile_num}'

    errors = []
    success_messages = []

    try:
        # Step 1: Delete docker-compose file if it exists
        if os.path.exists(compose_file):
            try:
                os.remove(compose_file)
                success_messages.append(f'File docker-compose.profile{profile_num}.yml deleted')
            except Exception as e:
                errors.append(f'Error deleting compose file: {str(e)}')
        else:
            success_messages.append(f'Compose file not found')

        # Step 2: Delete profile directory if it exists
        if os.path.exists(profile_dir):
            try:
                shutil.rmtree(profile_dir)
                success_messages.append(f'Profile directory profile{profile_num} deleted')
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
                'message': f'Profile {profile_num} files deleted successfully',
                'success': success_messages
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'success': success_messages,
            'errors': errors
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

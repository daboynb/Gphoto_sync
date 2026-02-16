#!/usr/bin/env python3
import json
import logging
import os
import time

import docker
from flask import Blueprint, Response, jsonify, stream_with_context

from utils import config
from utils.container_helpers import get_container_prefix
from utils.docker_client import docker_client
from utils.path_helpers import get_host_workspace_path
from utils.validators import validate_profile_name

logger = logging.getLogger(__name__)

healthcheck_bp = Blueprint('healthcheck', __name__)


@healthcheck_bp.route('/api/healthcheck/profiles', methods=['GET'])
def healthcheck_profiles():
    """List authenticated profiles available for health check."""
    profiles_dir = config.PROFILES_DIR
    if not os.path.exists(profiles_dir):
        return jsonify([])

    authenticated = []
    for name in sorted(os.listdir(profiles_dir)):
        profile_path = os.path.join(profiles_dir, name)
        if not os.path.isdir(profile_path):
            continue

        # Check for authentication cookies
        cookies_file = os.path.join(profile_path, 'Default', 'Cookies')
        has_cookies = os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0
        if not has_cookies:
            continue

        # Read display name from metadata
        display_name = name
        metadata_file = os.path.join(profile_path, '.profile_metadata.json')
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)
                display_name = metadata.get('display_name', name)
            except (OSError, json.JSONDecodeError):
                pass

        authenticated.append({
            'name': name,
            'display_name': display_name,
        })

    return jsonify(authenticated)


@healthcheck_bp.route('/api/healthcheck/<profile_name>/stream', methods=['POST'])
@validate_profile_name
def healthcheck_stream(profile_name):
    """Run health check container and stream results via SSE."""
    profile_path = os.path.join(config.PROFILES_DIR, profile_name)
    if not os.path.exists(profile_path):
        return jsonify({'error': f'Profile {profile_name} not found'}), 404

    def generate():
        container = None
        try:
            msg = json.dumps({'type': 'status', 'message': 'Starting health check container...'})
            yield f"data: {msg}\n\n"

            host_workspace = get_host_workspace_path()
            prefix = get_container_prefix()
            container_name = f'{prefix}-healthcheck-{profile_name}'

            # Remove any existing healthcheck container with same name
            try:
                old = docker_client.containers.get(container_name)
                old.remove(force=True)
            except docker.errors.NotFound:
                pass

            # Run one-shot container with healthcheck flag.
            # Override entrypoint to bypass start.sh (which sets up cron/users)
            # and run gphotos-cdp directly.
            container = docker_client.containers.run(
                image=f'{prefix}:latest',
                name=container_name,
                entrypoint=['gphotos-cdp'],
                command=[
                    '-healthcheck',
                    '-profile', '/tmp/gphotos-cdp',
                    '-headless',
                    '-json',
                    '-loglevel', 'info',
                ],
                volumes={
                    f'{host_workspace}/profiles/{profile_name}': {
                        'bind': '/tmp/gphotos-cdp',
                        'mode': 'rw',
                    },
                    f'{host_workspace}/gphotos-cdp/months-config.json': {
                        'bind': '/app/months-config.json',
                        'mode': 'ro',
                    },
                    f'{host_workspace}/gphotos-cdp/gphotos-cdp': {
                        'bind': '/usr/bin/gphotos-cdp',
                        'mode': 'ro',
                    },
                },
                privileged=True,
                detach=True,
                auto_remove=False,
            )

            msg = json.dumps({'type': 'status', 'message': 'Health check running...'})
            yield f"data: {msg}\n\n"

            # Stream container logs in real time
            for log_bytes in container.logs(stream=True, follow=True):
                line = log_bytes.decode('utf-8', errors='ignore').rstrip('\n')
                if not line:
                    continue

                # Try to parse as JSON test result or summary
                try:
                    data = json.loads(line)
                    if 'name' in data and 'status' in data:
                        msg = json.dumps({'type': 'test_result', 'data': data})
                        yield f"data: {msg}\n\n"
                        continue
                    if data.get('type') == 'summary':
                        msg = json.dumps({'type': 'summary', 'data': data})
                        yield f"data: {msg}\n\n"
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass

                # Regular log line
                msg = json.dumps({'type': 'log', 'message': line})
                yield f"data: {msg}\n\n"

            # Wait for container to finish (5 min timeout)
            try:
                result = container.wait(timeout=300)
            except Exception:
                logger.error("Health check timed out for profile '%s'", profile_name)
                msg = json.dumps({'type': 'error', 'message': 'Health check timed out after 5 minutes'})
                yield f"data: {msg}\n\n"
                return
            exit_code = result.get('StatusCode', -1)

            if exit_code == 0:
                msg = json.dumps({'type': 'complete', 'message': 'Health check completed successfully'})
            else:
                msg = json.dumps({'type': 'complete', 'message': f'Health check completed with exit code {exit_code}'})
            yield f"data: {msg}\n\n"

        except docker.errors.ImageNotFound:
            msg = json.dumps({'type': 'error', 'message': f'Docker image {get_container_prefix()}:latest not found. Build it first.'})
            yield f"data: {msg}\n\n"
        except docker.errors.APIError as exc:
            logger.error("Health check failed: %s", exc)
            msg = json.dumps({'type': 'error', 'message': f'Docker error: {str(exc)}'})
            yield f"data: {msg}\n\n"
        except Exception as exc:
            logger.error("Health check unexpected error: %s", exc)
            msg = json.dumps({'type': 'error', 'message': f'Error: {str(exc)}'})
            yield f"data: {msg}\n\n"
        finally:
            # Clean up container
            if container:
                try:
                    container.remove(force=True)
                except (docker.errors.NotFound, docker.errors.APIError):
                    pass

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

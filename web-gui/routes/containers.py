#!/usr/bin/env python3
import logging
from datetime import datetime

import docker
from flask import Blueprint, Response, jsonify, stream_with_context

from utils.container_helpers import get_container_info, get_sync_containers
from utils.docker_client import docker_client
from utils.validators import validate_container_id

logger = logging.getLogger(__name__)

containers_bp = Blueprint('containers', __name__)


def _parse_container_start_time(container):
    """Parse the container start time into a Unix timestamp."""
    started_at_str = container.attrs['State']['StartedAt']
    try:
        started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        started_at = datetime.strptime(started_at_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
    return int(started_at.timestamp())


@containers_bp.route('/api/containers')
def api_containers():
    """Get all container info."""
    containers = get_sync_containers()
    return jsonify([get_container_info(c) for c in containers])


@containers_bp.route('/api/container/<container_id>/logs')
@validate_container_id
def api_logs(container_id):
    """Get container logs (only from last boot)."""
    try:
        container = docker_client.containers.get(container_id)
        since_timestamp = _parse_container_start_time(container)
        logs = container.logs(since=since_timestamp, timestamps=True).decode('utf-8')
        return jsonify({'logs': logs})
    except docker.errors.NotFound:
        return jsonify({'error': f'Container {container_id} not found'}), 404
    except docker.errors.APIError as exc:
        logger.error("Error getting logs for %s: %s", container_id, exc)
        return jsonify({'error': str(exc)}), 500


@containers_bp.route('/api/container/<container_id>/logs/stream')
@validate_container_id
def stream_logs(container_id):
    """Stream container logs in real-time (only from last boot)."""
    def generate():
        try:
            container = docker_client.containers.get(container_id)

            container.reload()
            if container.status != 'running':
                yield f"event: close\ndata: Container stopped\n\n"
                return

            since_timestamp = _parse_container_start_time(container)

            try:
                for log in container.logs(stream=True, follow=True, timestamps=True, since=since_timestamp):
                    yield f"data: {log.decode('utf-8')}\n\n"

                    try:
                        container.reload()
                        if container.status != 'running':
                            yield f"event: close\ndata: Container stopped\n\n"
                            break
                    except docker.errors.APIError:
                        yield f"event: close\ndata: Container stopped or removed\n\n"
                        break
            except docker.errors.APIError:
                yield f"event: close\ndata: Stream ended\n\n"

        except docker.errors.NotFound:
            yield f"event: error\ndata: Container not found\n\n"
        except docker.errors.APIError as exc:
            yield f"event: error\ndata: {str(exc)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@containers_bp.route('/api/container/<container_id>/start', methods=['POST'])
@validate_container_id
def start_container(container_id):
    """Start a container."""
    try:
        container = docker_client.containers.get(container_id)
        container.start()
        return jsonify({'status': 'started'})
    except docker.errors.NotFound:
        return jsonify({'error': f'Container {container_id} not found'}), 404
    except docker.errors.APIError as exc:
        logger.error("Error starting container %s: %s", container_id, exc)
        return jsonify({'error': str(exc)}), 500


@containers_bp.route('/api/container/<container_id>/stop', methods=['POST'])
@validate_container_id
def stop_container(container_id):
    """Stop a container."""
    try:
        container = docker_client.containers.get(container_id)
        container.stop()
        return jsonify({'status': 'stopped'})
    except docker.errors.NotFound:
        return jsonify({'error': f'Container {container_id} not found'}), 404
    except docker.errors.APIError as exc:
        logger.error("Error stopping container %s: %s", container_id, exc)
        return jsonify({'error': str(exc)}), 500


@containers_bp.route('/api/container/<container_id>/restart', methods=['POST'])
@validate_container_id
def restart_container(container_id):
    """Restart a container."""
    try:
        container = docker_client.containers.get(container_id)
        container.restart()
        return jsonify({'status': 'restarted'})
    except docker.errors.NotFound:
        return jsonify({'error': f'Container {container_id} not found'}), 404
    except docker.errors.APIError as exc:
        logger.error("Error restarting container %s: %s", container_id, exc)
        return jsonify({'error': str(exc)}), 500


@containers_bp.route('/api/stats')
def api_stats():
    """Get overall stats."""
    containers = get_sync_containers()
    total = len(containers)
    running = sum(1 for c in containers if c.status == 'running')
    stopped = total - running

    return jsonify({
        'total': total,
        'running': running,
        'stopped': stopped,
    })

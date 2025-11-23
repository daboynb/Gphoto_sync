#!/usr/bin/env python3
from datetime import datetime
from flask import Blueprint, jsonify, Response, stream_with_context
from utils.docker_client import docker_client
from utils.container_helpers import get_sync_containers, get_container_info

containers_bp = Blueprint('containers', __name__)


@containers_bp.route('/api/containers')
def api_containers():
    """Get all container info"""
    containers = get_sync_containers()
    return jsonify([get_container_info(c) for c in containers])


@containers_bp.route('/api/container/<container_id>/logs')
def api_logs(container_id):
    """Get container logs (only from last boot)"""
    try:
        container = docker_client.containers.get(container_id)

        # Get container start time as ISO string
        started_at_str = container.attrs['State']['StartedAt']

        # Convert ISO string to datetime object
        # Handle both formats: with and without microseconds
        try:
            # Try parsing with microseconds (e.g., "2024-01-15T10:30:45.123456789Z")
            started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
        except:
            # Fallback: parse without microseconds
            started_at = datetime.strptime(started_at_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')

        # Convert to Unix timestamp (integer)
        since_timestamp = int(started_at.timestamp())

        # Get logs only since container started (last boot only)
        logs = container.logs(since=since_timestamp, timestamps=True).decode('utf-8')
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@containers_bp.route('/api/container/<container_id>/logs/stream')
def stream_logs(container_id):
    """Stream container logs in real-time (only from last boot)"""
    def generate():
        try:
            container = docker_client.containers.get(container_id)

            # Check if container is running
            container.reload()  # Refresh container state
            if container.status != 'running':
                # Send a close event to the client
                yield f"event: close\ndata: Container stopped\n\n"
                return

            # Get container start time as ISO string
            started_at_str = container.attrs['State']['StartedAt']

            # Convert ISO string to datetime object
            try:
                # Try parsing with microseconds (e.g., "2024-01-15T10:30:45.123456789Z")
                started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
            except:
                # Fallback: parse without microseconds
                started_at = datetime.strptime(started_at_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')

            # Convert to Unix timestamp (integer)
            since_timestamp = int(started_at.timestamp())

            # Stream logs only since container started (last boot only)
            try:
                for log in container.logs(stream=True, follow=True, timestamps=True, since=since_timestamp):
                    yield f"data: {log.decode('utf-8')}\n\n"

                    # Periodically check if container is still running
                    # Note: This will only trigger when new log lines arrive
                    try:
                        container.reload()
                        if container.status != 'running':
                            # Container stopped, send close event
                            yield f"event: close\ndata: Container stopped\n\n"
                            break
                    except:
                        # Container might have been removed
                        yield f"event: close\ndata: Container stopped or removed\n\n"
                        break
            except Exception as stream_error:
                # Stream was interrupted (likely because container stopped)
                yield f"event: close\ndata: Stream ended\n\n"

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@containers_bp.route('/api/container/<container_id>/start', methods=['POST'])
def start_container(container_id):
    """Start a container"""
    try:
        container = docker_client.containers.get(container_id)
        container.start()
        return jsonify({'status': 'started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@containers_bp.route('/api/container/<container_id>/stop', methods=['POST'])
def stop_container(container_id):
    """Stop a container"""
    try:
        container = docker_client.containers.get(container_id)
        container.stop()
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@containers_bp.route('/api/container/<container_id>/restart', methods=['POST'])
def restart_container(container_id):
    """Restart a container"""
    try:
        container = docker_client.containers.get(container_id)
        container.restart()
        return jsonify({'status': 'restarted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@containers_bp.route('/api/stats')
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

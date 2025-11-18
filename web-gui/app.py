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

    return {
        'id': container.id[:12],
        'name': container.name,
        'profile': profile_name,
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

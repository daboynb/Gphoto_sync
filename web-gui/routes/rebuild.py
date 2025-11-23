#!/usr/bin/env python3
import os
import json
import subprocess
import time
import docker
from datetime import datetime
from flask import Blueprint, Response, stream_with_context
from utils.docker_client import docker_client
from utils.container_helpers import get_sync_containers, get_container_prefix

rebuild_bp = Blueprint('rebuild', __name__)


@rebuild_bp.route('/api/rebuild-image/stream', methods=['GET'])
def rebuild_image_stream():
    """Stream rebuild progress in real-time using Server-Sent Events"""
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

            # Get current timestamp for build version
            build_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            image_version = datetime.now().strftime('%Y%m%d-%H%M%S')

            build_process = subprocess.Popen(
                [
                    'docker', 'build',
                    '--no-cache',
                    '--build-arg', f'BUILD_DATE={build_date}',
                    '--build-arg', f'IMAGE_VERSION={image_version}',
                    '-t', 'gphotos-sync:latest',
                    '.'
                ],
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

                # Second: Create container with fresh image (without starting it)
                msg = json.dumps({'type': 'log', 'message': f'  Creating container with fresh image...\n'})
                yield f"data: {msg}\n\n"

                recreate_process = subprocess.Popen(
                    ['docker', 'compose', '-f', compose_file, 'create', '--pull', 'never'],
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
                    error_msg = f'  ✗ Failed to recreate {profile_name}\n'
                    restart_errors.append(error_msg)
                    msg = json.dumps({'type': 'log', 'message': error_msg})
                    yield f"data: {msg}\n\n"
                else:
                    msg = json.dumps({'type': 'log', 'message': f'  ✓ {profile_name} recreated (use Start to run)\n'})
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

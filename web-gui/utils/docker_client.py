#!/usr/bin/env python3
import docker

# Initialize Docker client with explicit socket path
try:
    docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')
except Exception as e:
    print(f"Error connecting to Docker: {e}")
    docker_client = None

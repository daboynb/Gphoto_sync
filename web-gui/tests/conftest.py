#!/usr/bin/env python3
"""Shared test fixtures."""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure web-gui is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def mock_docker_client():
    """Provide a mocked Docker client."""
    with patch('utils.docker_client.docker_client') as mock_client:
        yield mock_client


@pytest.fixture
def app():
    """Create a Flask test application."""
    # Mock docker_client before importing app to avoid connection errors
    with patch('utils.docker_client.docker_client', MagicMock()):
        from app import app as flask_app
        flask_app.config['TESTING'] = True
        yield flask_app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace directory structure."""
    profiles_dir = tmp_path / 'profiles'
    profiles_dir.mkdir()
    photos_dir = tmp_path / 'photos'
    photos_dir.mkdir()
    return tmp_path

#!/usr/bin/env python3
"""Input validation helpers and Flask route decorators."""
import re
import functools
from flask import jsonify
from croniter import croniter

# Profile names: lowercase alphanumeric, hyphens, underscores. 2-64 chars.
_PROFILE_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$')

# Container IDs: 12-64 hex chars, or valid container names
_CONTAINER_ID_RE = re.compile(r'^[a-f0-9]{12,64}$')
_CONTAINER_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{3,}$')


def is_valid_profile_name(name):
    """Check if a profile name is safe for filesystem and Docker use."""
    if not name or '..' in name or '/' in name:
        return False
    return bool(_PROFILE_NAME_RE.match(name))


def is_valid_container_id(container_id):
    """Check if a container ID is a valid hex ID or container name."""
    if not container_id:
        return False
    return bool(_CONTAINER_ID_RE.match(container_id) or
                _CONTAINER_NAME_RE.match(container_id))


def is_valid_cron(expr):
    """Check if a cron expression is valid."""
    try:
        croniter(expr)
        return True
    except (ValueError, KeyError, TypeError):
        return False


def validate_profile_name(f):
    """Flask route decorator: returns 400 if profile_name is invalid."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        profile_name = kwargs.get('profile_name', '')
        if not is_valid_profile_name(profile_name):
            return jsonify({'error': f'Invalid profile name: {profile_name}'}), 400
        return f(*args, **kwargs)
    return wrapper


def validate_container_id(f):
    """Flask route decorator: returns 400 if container_id is invalid."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        container_id = kwargs.get('container_id', '')
        if not is_valid_container_id(container_id):
            return jsonify({'error': f'Invalid container ID: {container_id}'}), 400
        return f(*args, **kwargs)
    return wrapper

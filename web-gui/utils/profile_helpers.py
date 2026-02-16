#!/usr/bin/env python3
"""Helper functions for profile management."""
import json
import logging
import os
import re

from utils import config

logger = logging.getLogger(__name__)


def sanitize_profile_name(name):
    """Convert profile name to filesystem-safe format."""
    sanitized = re.sub(r'[^a-z0-9_-]', '_', name.lower().strip())
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')
    return sanitized if sanitized else 'profile'


def get_profile_metadata(profile_name):
    """Get profile metadata from metadata file."""
    metadata_file = os.path.join(config.PROFILES_DIR, profile_name, '.profile_metadata.json')
    try:
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read metadata for profile '%s': %s", profile_name, exc)
    return {'name': profile_name, 'display_name': profile_name}


def save_profile_metadata(profile_name, metadata):
    """Save profile metadata to the metadata file."""
    metadata_file = os.path.join(config.PROFILES_DIR, profile_name, '.profile_metadata.json')
    try:
        existing = get_profile_metadata(profile_name)
        existing.update(metadata)
        with open(metadata_file, 'w') as f:
            json.dump(existing, f, indent=2)
    except (OSError, TypeError) as exc:
        logger.warning("Could not save metadata for profile '%s': %s", profile_name, exc)


def extract_profile_name(container_name, prefix):
    """Extract profile name from a container name by removing the prefix."""
    result = container_name.replace(prefix + '-', '', 1)
    return result if result else 'default'

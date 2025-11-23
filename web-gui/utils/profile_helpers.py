#!/usr/bin/env python3
"""Helper functions for profile management"""
import os
import json
import re


def sanitize_profile_name(name):
    """Convert profile name to filesystem-safe format"""
    # Convert to lowercase, replace spaces/special chars with underscore
    sanitized = re.sub(r'[^a-z0-9_-]', '_', name.lower().strip())
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized if sanitized else 'profile'


def get_profile_metadata(profile_name):
    """Get profile metadata from metadata file"""
    metadata_file = f'/workspace/profiles/{profile_name}/.profile_metadata.json'
    try:
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'name': profile_name, 'display_name': profile_name}

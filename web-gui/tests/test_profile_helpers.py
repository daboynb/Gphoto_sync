#!/usr/bin/env python3
"""Tests for utils/profile_helpers.py."""
import json
import os
import pytest
from unittest.mock import patch

from utils.profile_helpers import (
    sanitize_profile_name,
    get_profile_metadata,
    save_profile_metadata,
    extract_profile_name,
)


class TestSanitizeProfileName:
    def test_lowercase(self):
        assert sanitize_profile_name('Family') == 'family'

    def test_spaces_to_underscores(self):
        assert sanitize_profile_name('My Photos') == 'my_photos'

    def test_special_chars(self):
        assert sanitize_profile_name('user@home!') == 'user_home'

    def test_multiple_underscores_collapsed(self):
        assert sanitize_profile_name('a___b') == 'a_b'

    def test_empty_returns_default(self):
        assert sanitize_profile_name('') == 'profile'

    def test_strips_leading_trailing_underscores(self):
        assert sanitize_profile_name('__test__') == 'test'


class TestGetProfileMetadata:
    def test_returns_metadata_from_file(self, tmp_workspace):
        profile_name = 'test-profile'
        profile_dir = tmp_workspace / 'profiles' / profile_name
        profile_dir.mkdir()
        metadata = {'name': profile_name, 'display_name': 'Test Profile'}
        (profile_dir / '.profile_metadata.json').write_text(json.dumps(metadata))

        with patch('utils.profile_helpers.config') as mock_config:
            mock_config.PROFILES_DIR = str(tmp_workspace / 'profiles')
            result = get_profile_metadata(profile_name)

        assert result['display_name'] == 'Test Profile'

    def test_returns_default_when_no_file(self, tmp_workspace):
        with patch('utils.profile_helpers.config') as mock_config:
            mock_config.PROFILES_DIR = str(tmp_workspace / 'profiles')
            result = get_profile_metadata('nonexistent')

        assert result == {'name': 'nonexistent', 'display_name': 'nonexistent'}


class TestSaveProfileMetadata:
    def test_saves_metadata(self, tmp_workspace):
        profile_name = 'test-profile'
        profile_dir = tmp_workspace / 'profiles' / profile_name
        profile_dir.mkdir()

        with patch('utils.profile_helpers.config') as mock_config:
            mock_config.PROFILES_DIR = str(tmp_workspace / 'profiles')
            save_profile_metadata(profile_name, {'photo_dir': '/custom/path'})

        metadata_file = profile_dir / '.profile_metadata.json'
        assert metadata_file.exists()
        data = json.loads(metadata_file.read_text())
        assert data['photo_dir'] == '/custom/path'


class TestExtractProfileName:
    def test_extracts_name(self):
        assert extract_profile_name('gphotos-sync-family', 'gphotos-sync') == 'family'

    def test_returns_full_name_when_no_suffix(self):
        # When container name equals prefix (no profile suffix), name is returned as-is
        assert extract_profile_name('gphotos-sync', 'gphotos-sync') == 'gphotos-sync'

    def test_preserves_compound_name(self):
        assert extract_profile_name('gphotos-sync-my-photos', 'gphotos-sync') == 'my-photos'

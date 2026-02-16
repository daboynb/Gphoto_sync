#!/usr/bin/env python3
"""Tests for utils/config.py."""
from utils import config


class TestConfigConstants:
    def test_timezone_is_string(self):
        assert isinstance(config.DEFAULT_TIMEZONE, str)
        assert config.DEFAULT_TIMEZONE == 'Europe/Rome'

    def test_cron_schedule_is_valid(self):
        parts = config.DEFAULT_CRON_SCHEDULE.split()
        assert len(parts) == 5

    def test_puid_pgid_are_ints(self):
        assert isinstance(config.DEFAULT_PUID, int)
        assert isinstance(config.DEFAULT_PGID, int)

    def test_paths_are_absolute(self):
        assert config.WORKSPACE_PATH.startswith('/')
        assert config.PROFILES_DIR.startswith('/')
        assert config.AUTH_DIR.startswith('/')
        assert config.PHOTOS_DIR.startswith('/')

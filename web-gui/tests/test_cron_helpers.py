#!/usr/bin/env python3
"""Tests for utils/cron_helpers.py."""
import pytest
from unittest.mock import patch

from utils.cron_helpers import parse_cron_next_run


class TestParseCronNextRun:
    def test_valid_cron_returns_next_run(self):
        result = parse_cron_next_run('0 3 * * *')
        assert result['next_run'] != 'N/A'
        assert 'h' in result['time_until']
        assert 'm' in result['time_until']

    def test_uses_default_timezone(self):
        with patch('utils.cron_helpers.config') as mock_config:
            mock_config.DEFAULT_TIMEZONE = 'Europe/Rome'
            result = parse_cron_next_run('0 3 * * *')
        assert result['next_run'] != 'N/A'

    def test_custom_timezone(self):
        result = parse_cron_next_run('0 3 * * *', tz='US/Eastern')
        assert result['next_run'] != 'N/A'

    def test_invalid_cron_returns_na(self):
        result = parse_cron_next_run('invalid')
        assert result['next_run'] == 'N/A'
        assert result['time_until'] == 'N/A'

    def test_every_minute(self):
        result = parse_cron_next_run('* * * * *')
        assert result['next_run'] != 'N/A'

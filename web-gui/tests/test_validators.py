#!/usr/bin/env python3
"""Tests for utils/validators.py."""
import pytest
from utils.validators import (
    is_valid_profile_name,
    is_valid_container_id,
    is_valid_cron,
)


# --- is_valid_profile_name ---

class TestIsValidProfileName:
    def test_valid_simple(self):
        assert is_valid_profile_name('family') is True

    def test_valid_with_hyphens(self):
        assert is_valid_profile_name('my-photos') is True

    def test_valid_with_underscores(self):
        assert is_valid_profile_name('my_photos') is True

    def test_valid_with_numbers(self):
        assert is_valid_profile_name('user123') is True

    def test_rejects_empty(self):
        assert is_valid_profile_name('') is False

    def test_rejects_dot_dot(self):
        assert is_valid_profile_name('a..b') is False

    def test_rejects_slash(self):
        assert is_valid_profile_name('a/b') is False

    def test_rejects_uppercase(self):
        assert is_valid_profile_name('Family') is False

    def test_rejects_single_char(self):
        assert is_valid_profile_name('a') is False

    def test_rejects_starts_with_hyphen(self):
        assert is_valid_profile_name('-abc') is False

    def test_rejects_spaces(self):
        assert is_valid_profile_name('my photos') is False

    def test_valid_two_chars(self):
        assert is_valid_profile_name('ab') is True

    def test_rejects_none(self):
        assert is_valid_profile_name(None) is False


# --- is_valid_container_id ---

class TestIsValidContainerId:
    def test_valid_hex_12(self):
        assert is_valid_container_id('abcdef012345') is True

    def test_valid_hex_64(self):
        assert is_valid_container_id('a' * 64) is True

    def test_valid_container_name(self):
        assert is_valid_container_id('gphotos-sync-family') is True

    def test_rejects_empty(self):
        assert is_valid_container_id('') is False

    def test_rejects_short_hex(self):
        assert is_valid_container_id('abc') is False

    def test_rejects_none(self):
        assert is_valid_container_id(None) is False


# --- is_valid_cron ---

class TestIsValidCron:
    def test_valid_standard(self):
        assert is_valid_cron('0 3 * * *') is True

    def test_valid_every_minute(self):
        assert is_valid_cron('* * * * *') is True

    def test_valid_complex(self):
        assert is_valid_cron('0 */2 * * 1-5') is True

    def test_invalid_expression(self):
        assert is_valid_cron('not a cron') is False

    def test_empty_string(self):
        assert is_valid_cron('') is False

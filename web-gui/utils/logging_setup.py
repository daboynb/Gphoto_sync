#!/usr/bin/env python3
"""Logging configuration with JSON output consistent with the Go sync engine."""
import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Produce JSON log lines matching the Go sync engine format."""

    def format(self, record):
        log_entry = {
            'time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'level': record.levelname.lower(),
            'msg': record.getMessage(),
            'module': record.name,
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry['error'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level=logging.INFO):
    """Configure application-wide logging. Call once in app.py."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Reduce noise from third-party libraries
    for noisy in ('urllib3', 'docker', 'werkzeug'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

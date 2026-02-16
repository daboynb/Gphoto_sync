#!/usr/bin/env python3
"""Helper functions for cron scheduling."""
import logging
from datetime import datetime

import pytz
from croniter import croniter

from utils import config

logger = logging.getLogger(__name__)


def parse_cron_next_run(cron_schedule, tz=None):
    """Calculate next run time from cron schedule."""
    if tz is None:
        tz = config.DEFAULT_TIMEZONE
    try:
        timezone = pytz.timezone(tz)
        base_time = datetime.now(timezone)

        cron = croniter(cron_schedule, base_time)
        next_run = cron.get_next(datetime)

        time_until = next_run - base_time
        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)

        return {
            'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S'),
            'time_until': f"{hours}h {minutes}m",
        }
    except (ValueError, KeyError) as exc:
        logger.warning("Invalid cron schedule '%s': %s", cron_schedule, exc)
        return {'next_run': 'N/A', 'time_until': 'N/A'}

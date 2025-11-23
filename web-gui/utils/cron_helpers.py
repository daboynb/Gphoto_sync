#!/usr/bin/env python3
"""Helper functions for cron scheduling"""
from datetime import datetime
from croniter import croniter
import pytz


def parse_cron_next_run(cron_schedule, tz='Europe/Rome'):
    """Calculate next run time from cron schedule"""
    try:
        # Get timezone-aware current time
        timezone = pytz.timezone(tz)
        base_time = datetime.now(timezone)

        # Calculate next cron run
        cron = croniter(cron_schedule, base_time)
        next_run = cron.get_next(datetime)

        # Calculate time difference
        time_until = next_run - base_time

        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)

        return {
            'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S'),
            'time_until': f"{hours}h {minutes}m"
        }
    except Exception as e:
        return {'next_run': 'N/A', 'time_until': 'N/A'}

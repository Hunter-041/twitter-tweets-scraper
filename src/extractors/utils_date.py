thonfrom __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as dt_parser

logger = logging.getLogger(__name__)

def default_since_date() -> datetime:
    """
    Default 'since' value: start of yesterday in UTC.
    This gives users a reasonable default time window without overwhelming results.
    """
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    return datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=timezone.utc)

def parse_since_date(value: str) -> Optional[datetime]:
    """
    Parse a user-supplied date or datetime string.

    Supported formats include:
    - 2024-03-05
    - 2024-03-05T00:00:00
    - Any ISO-8601 format understood by dateutil.parser
    """
    if not value:
        return None

    try:
        dt = dt_parser.parse(value)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as exc:
        logger.error("Could not parse since_date '%s': %s", value, exc)
        return None

def parse_twitter_timestamp(value: str) -> Optional[datetime]:
    """
    Parse Twitter-style timestamps such as:
        Wed Mar 06 10:00:39 +0000 2024
    and more generic ISO strings.
    """
    if not value:
        return None

    try:
        dt = dt_parser.parse(value)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as exc:
        logger.debug("Failed to parse Twitter timestamp '%s': %s", value, exc)
        return None
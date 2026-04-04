"""
Cron and interval parsing utilities.

Handles parsing of interval strings (e.g., '1h', '30m') and cron expressions.
"""
import re


def parse_interval(interval_str: str) -> dict[str, int]:
    """
    Parse interval string like '1h', '30m', '10s', '2d' to APScheduler kwargs.

    Args:
        interval_str: Interval string in format <number><unit> where unit is:
            - s: seconds
            - m: minutes
            - h: hours
            - d: days

    Returns:
        Dictionary with APScheduler IntervalTrigger kwargs.

    Raises:
        ValueError: If the interval format is invalid.

    Examples:
        >>> parse_interval('1h')
        {'hours': 1}
        >>> parse_interval('30m')
        {'minutes': 30}
        >>> parse_interval('10s')
        {'seconds': 10}
    """
    match = re.match(r'^(\d+)([smhd])$', interval_str.lower())
    if not match:
        raise ValueError(f"Invalid interval format: {interval_str}")

    value = int(match.group(1))
    unit = match.group(2)

    unit_map = {
        's': 'seconds',
        'm': 'minutes',
        'h': 'hours',
        'd': 'days'
    }
    return {unit_map[unit]: value}


def is_cron_expression(schedule: str) -> bool:
    """
    Determine if a schedule string is a cron expression or interval.

    Args:
        schedule: Schedule string to check.

    Returns:
        True if the string appears to be a cron expression, False otherwise.

    Examples:
        >>> is_cron_expression('0 * * * *')
        True
        >>> is_cron_expression('*/5 * * * *')
        True
        >>> is_cron_expression('1h')
        False
    """
    # Cron expressions typically have:
    # - Multiple space-separated fields (5 or 6)
    # - Asterisks, slashes, or commas
    if any(c in schedule for c in ["*", "/"]) or len(schedule.split()) >= 5:
        return True
    return False

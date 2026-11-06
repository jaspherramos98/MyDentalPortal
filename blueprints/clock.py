# File: MyDentalPortal/blueprints/clock.py
# The one place the app reads "now" in UTC.

from datetime import datetime, timezone


def utcnow():
    """Current UTC time as a NAIVE datetime.

    Replaces the deprecated ``datetime.utcnow()`` with the same shape: pymongo
    returns stored datetimes naive (UTC) by default, and comparing a naive value
    with an aware one raises TypeError — so everything we write and compare
    stays naive UTC.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clinic_today(tz_name='Asia/Manila'):
    """Today's date as 'YYYY-MM-DD' in the clinic's timezone.

    Appointment/treatment dates are stored as local 'YYYY-MM-DD' strings, so
    "is this in the past?" must use the clinic's calendar day, not UTC's
    (Manila is UTC+8 — UTC still says "yesterday" until 8 AM).
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name)).strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')

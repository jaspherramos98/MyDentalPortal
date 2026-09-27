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

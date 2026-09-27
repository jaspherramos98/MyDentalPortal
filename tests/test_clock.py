"""blueprints.clock.utcnow: naive UTC, so it compares cleanly with what pymongo returns."""
from datetime import datetime, timedelta, timezone

from blueprints.clock import utcnow


def test_utcnow_is_naive_utc():
    now = utcnow()
    assert now.tzinfo is None
    reference = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs(now - reference) < timedelta(seconds=2)


def test_utcnow_compares_with_stored_naive_datetimes(db):
    db.things.insert_one({"expires_at": utcnow() + timedelta(days=1)})
    stored = db.things.find_one({})["expires_at"]
    assert stored > utcnow()          # would raise TypeError if one side were tz-aware

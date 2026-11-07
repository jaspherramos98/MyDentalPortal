# File: MyDentalPortal/blueprints/ages.py
# Patient age is DERIVED from the birthday, never trusted from storage.
#
# The stored `personal_info.age` is a snapshot from the day the record was
# saved, so it goes stale on every birthday. Everything that shows an age
# (detail, list, PDFs) goes through current_age(); saves store age_on(...) so
# the snapshot is at least right on the day it's written. The stored value is
# only shown for legacy records that have no (valid) birthday.

from datetime import date

MAX_AGE = 150


def _parse(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def age_on(birthday, today):
    """Whole years from `birthday` to `today` ('YYYY-MM-DD' strings or dates).

    None when either date is missing/malformed, the birthday is in the future,
    or the result is implausible (> MAX_AGE).
    """
    born, now = _parse(birthday), _parse(today)
    if born is None or now is None or born > now:
        return None
    years = now.year - born.year - ((now.month, now.day) < (born.month, born.day))
    return years if years <= MAX_AGE else None


def display_age(personal_info, today):
    """Age to show: computed from the birthday, else the stored legacy value, else None."""
    pi = personal_info or {}
    computed = age_on(pi.get('birthday'), today)
    if computed is not None:
        return computed
    stored = pi.get('age')
    return stored if stored not in (None, '') else None


def current_age(personal_info):
    """display_age() as of today in the clinic's timezone (needs an app context)."""
    from flask import current_app
    from blueprints.clock import clinic_today
    return display_age(personal_info, clinic_today(current_app.config.get('TIMEZONE', 'Asia/Manila')))


def age_to_store(birthday, typed_age, today):
    """Value to save in personal_info.age: computed from the birthday when valid,
    otherwise the typed age (trimmed) for patients whose birthday is unknown."""
    computed = age_on(birthday, today)
    if computed is not None:
        return str(computed)
    return (typed_age or '').strip()

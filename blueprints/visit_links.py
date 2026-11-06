# File: MyDentalPortal/blueprints/visit_links.py
# Rules for attaching treatment records to a calendar visit (appointment) and
# marking the visit completed. Used by the calendar's Record-visit dialog and the
# Add Treatment form, so both enforce the same checks.
#
# The link lives on the treatment only (``treatment.appointment_id``); the
# visit's outcome is derived from its treatments (see blueprints/visits.py).

from datetime import date, timedelta

from blueprints.repositories import appointments as appt_repo
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import treatments as treatment_repo
from blueprints.utils import audit

# A record dated up to this many days after the visit may be linked to it
# (entered late, e.g. the next morning).
LINK_WINDOW_DAYS = 30
# Add Treatment offers still-open visits from this far back.
OPEN_VISIT_LOOKBACK_DAYS = 30

COMPLETABLE_STATUSES = ('scheduled', 'completed')


def _shift(day, days):
    """'YYYY-MM-DD' moved by `days` (same format)."""
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def visit_clinic(appt, user_id):
    """The appointment's clinic if the user may work in it, else None."""
    if not appt or not appt.get('is_active'):
        return None
    return clinic_repo.get_accessible(appt['clinic_id'], user_id)


def refusal(appt, patient, user_id, today):
    """Why treatments of `patient` can't be attached to `appt` (None = they can).

    The appointment may be in a different clinic than the patient's own (one
    dentist with two clinics books patients at either); what matters is that the
    user may work in the appointment's clinic. Messages are user-safe.
    """
    if not visit_clinic(appt, user_id):
        return 'Appointment not found.'
    if appt.get('status', 'scheduled') not in COMPLETABLE_STATUSES:
        return 'Reactivate this appointment before recording the visit.'
    if appt.get('date', '') > today:
        return "This appointment hasn't happened yet."
    if appt.get('patient_id') and appt['patient_id'] != patient['_id']:
        return 'This appointment is booked for a different patient.'
    return None


def linkable_appointment(appointment_id, patient, user_id, today):
    """The appointment (by untrusted id) if `patient`'s treatments may be
    attached to it, else None."""
    if not appointment_id:
        return None
    appt = appt_repo.get(appointment_id)
    if not appt or refusal(appt, patient, user_id, today):
        return None
    return appt


def link_candidates(appt, patient_id, today):
    """The patient's unlinked treatments dated from the visit up to
    LINK_WINDOW_DAYS later (never past today) — records entered without going
    through the visit, which it can claim."""
    start = appt['date']
    end = min(today, _shift(start, LINK_WINDOW_DAYS))
    if end < start:
        return []
    return treatment_repo.unlinked_for_patient(patient_id, start, end)


def open_visits(patient_id, clinic_ids, today):
    """The patient's still-scheduled visits from the last OPEN_VISIT_LOOKBACK_DAYS
    up to today (Add Treatment offers to complete one)."""
    if not clinic_ids:
        return []
    return appt_repo.open_for_patient(patient_id, clinic_ids,
                                      _shift(today, -OPEN_VISIT_LOOKBACK_DAYS), today)


def complete(appt, patient, clinic):
    """Mark the visit completed once a treatment is attached (idempotent: a retry
    or a second procedure re-runs this harmlessly). Links a typed-in walk-in to
    the registered patient. ``clinic`` = the appointment's clinic (audit scope)."""
    if appt.get('status') == 'completed' and appt.get('patient_id'):
        return
    appt_repo.mark_completed(appt['_id'],
                             patient_id=None if appt.get('patient_id') else patient['_id'])
    audit('complete', 'appointment', str(appt['_id']), clinic=clinic)

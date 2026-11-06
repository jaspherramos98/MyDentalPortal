# File: MyDentalPortal/blueprints/treatment_records.py
# Building a new treatment record from user input — shared by the full Add
# Treatment form and the calendar's quick "Record visit" dialog, so both apply
# the same parsing, defaults and price-confirmation rule.

import math

from bson.objectid import ObjectId

from blueprints.clock import utcnow

# The procedure picker (Add Treatment form + Record visit dialog).
PROCEDURES = (
    'Oral Prophylaxis', 'OP + Fluoride Treatment', 'Tooth Extraction',
    'Restoration (Filling)', 'Root Canal Treatment', 'Crown / Bridge', 'Denture',
    'Orthodontic Adjustment', 'Tooth Whitening', 'Fluoride Treatment', 'Sealant',
    'Consultation', 'X-ray', 'Surgery', 'Other',
)

# Free-text "next visit" note (e.g. "2 weeks — crown fitting"). Separate from
# the Schedule-Next-Appointment button, which books a real calendar slot.
NEXT_VISIT_MAX_LEN = 200
PROCEDURE_MAX_LEN = 200
TEXT_MAX_LEN = 2000


class TreatmentInputError(ValueError):
    """User input that can't become a treatment record (message is user-safe)."""


def _text(values, key, limit=TEXT_MAX_LEN):
    return str(values.get(key) or '').strip()[:limit]


def money(value):
    """A non-negative, finite amount from form/JSON input ('' / None -> 0)."""
    if value in (None, ''):
        return 0.0
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise TreatmentInputError('Amounts must be numbers.')
    if not math.isfinite(amount) or amount < 0:
        raise TreatmentInputError("Amounts can't be negative.")
    return round(amount, 2)


def next_visit(values):
    """The trimmed Next Visit note, capped at NEXT_VISIT_MAX_LEN characters."""
    return _text(values, 'next_visit', NEXT_VISIT_MAX_LEN)


def new_treatment(values, patient_id, clinic, user_id, user_name, confirmer, today):
    """The document for a new treatment record.

    ``values`` is a form or JSON dict. ``clinic`` is the PATIENT's clinic (the
    record lives with the patient). ``confirmer`` = dentist/admin: their price is
    confirmed at once; a staff member's price is pending until a dentist
    confirms it. Raises TreatmentInputError for unusable input.
    """
    procedure = _text(values, 'procedure', PROCEDURE_MAX_LEN)
    if not procedure:
        raise TreatmentInputError('Pick the procedure that was done.')
    charged = money(values.get('amount_charged'))
    paid = money(values.get('amount_paid'))
    tooth = values.get('tooth_numbers') or ''
    if isinstance(tooth, str):
        tooth = tooth.split(',')
    now = utcnow()
    return {
        'patient_id': patient_id if isinstance(patient_id, ObjectId) else ObjectId(patient_id),
        'clinic_id': clinic['_id'],
        'date': _text(values, 'date', 10) or today,
        'tooth_numbers': [str(t).strip()[:20] for t in tooth if str(t).strip()][:32],
        'procedure': procedure,
        'description': _text(values, 'description'),
        'dentist': _text(values, 'dentist', PROCEDURE_MAX_LEN) or (user_name or ''),
        'amount_charged': charged,
        'amount_paid': paid,
        'balance': charged - paid,
        'currency': clinic.get('currency', 'PHP'),
        'status': _text(values, 'status', 20) or 'completed',
        'notes': _text(values, 'notes'),
        'next_appointment': _text(values, 'next_appointment', 100),
        'next_visit': next_visit(values),
        'created_by': user_id,
        'created_at': now,
        'updated_at': now,
        'price_set_by': user_id,
        'price_confirmed': bool(confirmer),
        'price_confirmed_by': user_id if confirmer else None,
        'price_confirmed_at': now if confirmer else None,
    }

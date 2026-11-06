# File: MyDentalPortal/blueprints/visits.py
# The OUTCOME of an appointment ("visit"), derived from the appointment's status
# and the treatment records linked to it (``treatment.appointment_id``).
#
# Nothing here is stored: the outcome is recomputed on every read, so marking a
# treatment paid or confirming its price updates the calendar/list immediately
# with no second write to keep in sync. Pure functions — no DB, no Flask.

from dataclasses import dataclass, field

# Visit states (what the calendar banner / list icon shows).
STATE_UPCOMING = 'upcoming'     # scheduled, day not over yet — a normal calendar block
STATE_DONE = 'done'             # ✅ completed, fully paid, price confirmed
STATE_CANCELLED = 'cancelled'   # ❌ cancelled OR no-show (status stays distinct in data)
STATE_ATTENTION = 'attention'   # 🟠 needs follow-up — see `reasons`

# Attention reasons (shown on tap; amounts deliberately NOT included).
REASON_NOT_MARKED = 'Not marked'
REASON_NO_TREATMENT = 'No treatment record'
REASON_BALANCE = 'Balance due'
REASON_PRICE_PENDING = 'Price pending'

STATUS_LABELS = {
    'scheduled': 'Scheduled',
    'completed': 'Completed',
    'cancelled': 'Cancelled',
    'no-show': 'No-show',
}


@dataclass(frozen=True)
class Visit:
    state: str
    status_label: str
    reasons: list = field(default_factory=list)
    procedures: list = field(default_factory=list)
    charged: float = 0.0
    balance: float = 0.0

    @property
    def has_banner(self):
        """Past/finished visits render as a compact banner on the calendar."""
        return self.state != STATE_UPCOMING


def treatment_balance(treatment):
    """Outstanding amount on one treatment, never negative.

    Computed from charged - paid rather than trusting the stored ``balance``
    field, so a legacy record with a stale balance can't show the wrong icon.
    """
    charged = float(treatment.get('amount_charged') or 0)
    paid = float(treatment.get('amount_paid') or 0)
    return max(round(charged - paid, 2), 0.0)


def summarize(appointment, treatments, today):
    """The Visit for one appointment.

    `treatments` = the records linked to it (may be empty); `today` = the
    clinic's local date as 'YYYY-MM-DD' (dates are stored in that format, so
    string comparison is chronological).
    """
    status = appointment.get('status') or 'scheduled'
    label = STATUS_LABELS.get(status, status.title())
    procedures = [t.get('procedure') for t in treatments if t.get('procedure')]
    charged = round(sum(float(t.get('amount_charged') or 0) for t in treatments), 2)
    balance = round(sum(treatment_balance(t) for t in treatments), 2)
    totals = dict(procedures=procedures, charged=charged, balance=balance)

    if status in ('cancelled', 'no-show'):
        return Visit(STATE_CANCELLED, label, **totals)

    if status == 'completed':
        reasons = []
        if not treatments:
            reasons.append(REASON_NO_TREATMENT)
        if balance > 0:
            reasons.append(REASON_BALANCE)
        # Legacy treatments have no field and count as confirmed (matches the
        # pending-prices queue's `== False` rule).
        if any(t.get('price_confirmed', True) is False for t in treatments):
            reasons.append(REASON_PRICE_PENDING)
        state = STATE_ATTENTION if reasons else STATE_DONE
        return Visit(state, label, reasons, **totals)

    if (appointment.get('date') or '') < today:
        return Visit(STATE_ATTENTION, label, [REASON_NOT_MARKED], **totals)
    return Visit(STATE_UPCOMING, label, **totals)

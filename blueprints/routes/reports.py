# File: MyDentalPortal/blueprints/routes/reports.py
# Sales / performance reporting — aggregates treatment revenue, procedures,
# collections and patient growth for the clinics owned by the current user.
#
# All figures are scoped to the logged-in owner's clinics (optionally a single
# selected clinic). Treatment `date` is stored as a 'YYYY-MM-DD' string, so the
# date-range filter uses a lexicographic comparison (valid for that format) and
# monthly bucketing is done in Python.

from flask import (
    Blueprint, render_template, session, request,
)
from bson.objectid import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timedelta
from collections import defaultdict

from blueprints.utils import login_required, user_clinic_ids
from blueprints.repositories import clinics as clinic_repo
from blueprints.repositories import treatments as treatment_repo
from blueprints.repositories import patients as patient_repo

reports_bp = Blueprint('reports', __name__)

CURRENCY_SYMBOLS = {'PHP': '₱', 'USD': '$'}

# Period options shown in the selector → human label. The two short ranges
# (today / this week) bucket the time-series by DAY; the rest bucket by MONTH
# (a daily axis over months would be unreadable, a monthly axis over a day or
# week would collapse to a single bar).
PERIODS = {
    'today': 'Today',
    'thisweek': 'This week',
    'thismonth': 'This month',
    '6m': 'Last 6 months',
    '12m': 'Last 12 months',
    'all': 'All time',
}
DAY_BUCKET_RANGES = {'today', 'thisweek'}


def _add_months(d, n):
    """First day of the month that is `n` months from month-start of `d`."""
    m = d.month - 1 + n
    y = d.year + m // 12
    return datetime(y, m % 12 + 1, 1)


def _month_range(start, end):
    """List of 'YYYY-MM' labels from `start` to `end` inclusive."""
    labels, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        labels.append('%04d-%02d' % (y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return labels


def _fmt(symbol, amount):
    """Money string with thousands separators, e.g. '₱12,500.00'."""
    return '%s%s' % (symbol, '{:,.2f}'.format(amount or 0))


@reports_bp.route('/reports')
@login_required
def reports():
    all_clinic_ids = user_clinic_ids()
    clinics = clinic_repo.owned_active_by_name(session['user_id'])

    # ── clinic filter ──
    sel = request.args.get('clinic') or ''
    sel_oid = None
    if sel:
        try:
            cand = ObjectId(sel)
            if cand in all_clinic_ids:
                sel_oid = cand
        except (InvalidId, TypeError):
            sel_oid = None
    scope_ids = [sel_oid] if sel_oid else all_clinic_ids

    # ── currency (one clinic == one currency; flag if mixed across clinics) ──
    scoped_clinics = [c for c in clinics if (not sel_oid or c['_id'] == sel_oid)]
    currencies = {c.get('currency', 'PHP') for c in scoped_clinics} or {'PHP'}
    mixed_currency = len(currencies) > 1
    currency_code = next(iter(currencies)) if not mixed_currency else 'PHP'
    symbol = CURRENCY_SYMBOLS.get(currency_code, '')

    # ── period ──
    # Default to "all time" so a clinic's older treatments are never silently
    # hidden behind a rolling window — the user narrows down with the selector.
    rng = request.args.get('range', 'all')
    if rng not in PERIODS:
        rng = 'all'
    period_label = PERIODS[rng]
    bucket = 'day' if rng in DAY_BUCKET_RANGES else 'month'

    today = datetime.now()
    today_start = datetime(today.year, today.month, today.day)
    this_month = datetime(today.year, today.month, 1)
    if rng == 'today':
        start_dt = today_start
    elif rng == 'thisweek':
        start_dt = today_start - timedelta(days=today.weekday())  # Monday
    elif rng == 'thismonth':
        start_dt = this_month
    elif rng == '6m':
        start_dt = _add_months(this_month, -5)
    elif rng == '12m':
        start_dt = _add_months(this_month, -11)
    else:  # 'all'
        start_dt = None
    start_str = start_dt.strftime('%Y-%m-%d') if start_dt else None
    # Key length / strftime used to bucket a date into the series.
    key_len = 10 if bucket == 'day' else 7
    key_fmt = '%Y-%m-%d' if bucket == 'day' else '%Y-%m'

    # ── empty scope short-circuit ──
    if not scope_ids:
        return render_template(
            'reports/index.html', clinics=clinics, selected_clinic=sel,
            selected_range=rng, period_label=period_label, bucket=bucket,
            has_data=False, symbol=symbol,
            mixed_currency=mixed_currency, kpis={}, charts={},
        )

    # ── treatments ──
    treatments = treatment_repo.find_for_clinics(scope_ids, start_date=start_str, fields={
        'date': 1, 'amount_charged': 1, 'amount_paid': 1, 'balance': 1,
        'procedure': 1, 'status': 1,
    })

    # Period-scoped figures (revenue/billed in the selected window + time series).
    total_billed = total_paid = 0.0
    monthly_paid = defaultdict(float)
    monthly_billed = defaultdict(float)
    proc_rev = defaultdict(float)
    status_count = defaultdict(int)
    earliest = None

    for t in treatments:
        charged = float(t.get('amount_charged') or 0)
        paid = float(t.get('amount_paid') or 0)
        total_billed += charged
        total_paid += paid

        d = (t.get('date') or '')[:key_len]   # 'YYYY-MM' or 'YYYY-MM-DD'
        if len(d) == key_len:
            monthly_paid[d] += paid
            monthly_billed[d] += charged
            if earliest is None or d < earliest:
                earliest = d

        proc = (t.get('procedure') or '').strip() or 'Unspecified'
        proc_rev[proc] += paid
        status_count[(t.get('status') or 'completed').strip().lower()] += 1

    # ── all-time accounts-receivable (point in time, NOT period-scoped) ──
    # Outstanding balance and lifetime collections are "as of now" figures: an
    # old unpaid treatment is still owed today, and clearing any balance must
    # always reduce it regardless of the selected period. So these are summed
    # across every treatment in scope, ignoring the date filter.
    all_collected = all_outstanding = 0.0
    for t in treatment_repo.find_for_clinics(scope_ids, fields={
        'amount_charged': 1, 'amount_paid': 1, 'balance': 1,
    }):
        charged = float(t.get('amount_charged') or 0)
        paid = float(t.get('amount_paid') or 0)
        bal = t.get('balance')
        bal = float(bal) if bal is not None else (charged - paid)
        all_collected += paid
        if bal > 0:
            all_outstanding += bal

    # ── new patients (created_at is a real datetime) ──
    monthly_new = defaultdict(int)
    new_patients = 0
    for p in patient_repo.find_active_in_clinics(
        scope_ids, created_since=start_dt, fields={'created_at': 1},
    ):
        new_patients += 1
        ca = p.get('created_at')
        if isinstance(ca, datetime):
            key = ca.strftime(key_fmt)
            monthly_new[key] += 1
            if earliest is None or key < earliest:
                earliest = key

    # ── time axis ──
    if bucket == 'day':
        # Daily axis from the window start to today inclusive (today = 1 day,
        # this week = up to 7). start_dt is always set for day buckets.
        month_keys = []
        d = start_dt
        while d <= today_start:
            month_keys.append(d.strftime('%Y-%m-%d'))
            d += timedelta(days=1)
        month_labels = [datetime.strptime(k, '%Y-%m-%d').strftime('%b %d') for k in month_keys]
    else:
        if start_dt is None:
            # "All time": start at the earliest data month, but cap the axis to a
            # trailing 24-month window so stray/old dates can't render a giant chart.
            try:
                earliest_dt = datetime.strptime((earliest or this_month.strftime('%Y-%m')) + '-01', '%Y-%m-%d')
            except ValueError:
                earliest_dt = this_month
            first = max(earliest_dt, _add_months(this_month, -23))
            if first > this_month:
                first = this_month
        else:
            first = start_dt
        month_keys = _month_range(first, this_month)
        # Friendly labels: 'Jan 2026'
        month_labels = [datetime.strptime(k + '-01', '%Y-%m-%d').strftime('%b %Y') for k in month_keys]

    # ── top procedures (top 8 by revenue, rest → 'Other') ──
    proc_sorted = sorted(proc_rev.items(), key=lambda kv: kv[1], reverse=True)
    top_procs = proc_sorted[:8]
    other_total = sum(v for _, v in proc_sorted[8:])
    proc_labels = [p for p, _ in top_procs]
    proc_values = [round(v, 2) for _, v in top_procs]
    if other_total > 0:
        proc_labels.append('Other')
        proc_values.append(round(other_total, 2))

    treatment_count = len(treatments)
    avg_per = (total_paid / treatment_count) if treatment_count else 0
    collection_rate = (total_paid / total_billed * 100) if total_billed else 0

    kpis = {
        'total_paid': _fmt(symbol, total_paid),
        'total_billed': _fmt(symbol, total_billed),
        'total_outstanding': _fmt(symbol, all_outstanding),
        'treatment_count': treatment_count,
        'new_patients': new_patients,
        'avg_per': _fmt(symbol, avg_per),
        'collection_rate': '{:.0f}%'.format(collection_rate),
    }

    charts = {
        'month_labels': month_labels,
        'monthly_paid': [round(monthly_paid.get(k, 0), 2) for k in month_keys],
        'monthly_billed': [round(monthly_billed.get(k, 0), 2) for k in month_keys],
        'monthly_new': [monthly_new.get(k, 0) for k in month_keys],
        'proc_labels': proc_labels,
        'proc_values': proc_values,
        'status_labels': [s.title() for s in status_count.keys()],
        'status_values': list(status_count.values()),
        'collected': round(all_collected, 2),
        'outstanding': round(all_outstanding, 2),
        'symbol': symbol,
    }

    return render_template(
        'reports/index.html',
        clinics=clinics,
        selected_clinic=sel,
        selected_range=rng,
        period_label=period_label,
        bucket=bucket,
        has_data=(treatment_count > 0 or new_patients > 0),
        symbol=symbol,
        mixed_currency=mixed_currency,
        kpis=kpis,
        charts=charts,
    )

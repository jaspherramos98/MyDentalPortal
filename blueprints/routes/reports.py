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
from datetime import datetime
from collections import defaultdict

from extensions import mongo
from blueprints.utils import login_required, user_clinic_ids

reports_bp = Blueprint('reports', __name__)

CURRENCY_SYMBOLS = {'PHP': '₱', 'USD': '$'}

# Period options shown in the selector → number of months back (None = all time).
RANGES = {
    'thismonth': 0,
    '6m': 5,
    '12m': 11,
    'all': None,
}


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
    clinics = list(
        mongo.db.clinics.find({'owner_id': session['user_id'], 'is_active': True})
        .sort('name', 1)
    )

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
    rng = request.args.get('range', '12m')
    if rng not in RANGES:
        rng = '12m'
    today = datetime.now()
    this_month = datetime(today.year, today.month, 1)
    months_back = RANGES[rng]
    start_dt = None if months_back is None else _add_months(this_month, -months_back)
    start_str = start_dt.strftime('%Y-%m-%d') if start_dt else None

    # ── empty scope short-circuit ──
    if not scope_ids:
        return render_template(
            'reports/index.html', clinics=clinics, selected_clinic=sel,
            selected_range=rng, has_data=False, symbol=symbol,
            mixed_currency=mixed_currency, kpis={}, charts={},
        )

    # ── treatments ──
    tq = {'clinic_id': {'$in': scope_ids}}
    if start_str:
        tq['date'] = {'$gte': start_str}
    treatments = list(mongo.db.treatment_records.find(tq, {
        'date': 1, 'amount_charged': 1, 'amount_paid': 1, 'balance': 1,
        'procedure': 1, 'status': 1,
    }))

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

        d = (t.get('date') or '')[:7]   # 'YYYY-MM'
        if len(d) == 7:
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
    for t in mongo.db.treatment_records.find(
        {'clinic_id': {'$in': scope_ids}},
        {'amount_charged': 1, 'amount_paid': 1, 'balance': 1},
    ):
        charged = float(t.get('amount_charged') or 0)
        paid = float(t.get('amount_paid') or 0)
        bal = t.get('balance')
        bal = float(bal) if bal is not None else (charged - paid)
        all_collected += paid
        if bal > 0:
            all_outstanding += bal

    # ── new patients (created_at is a real datetime) ──
    pq = {'clinic_id': {'$in': scope_ids}, 'is_active': True}
    if start_dt:
        pq['created_at'] = {'$gte': start_dt}
    monthly_new = defaultdict(int)
    new_patients = 0
    for p in mongo.db.patients.find(pq, {'created_at': 1}):
        new_patients += 1
        ca = p.get('created_at')
        if isinstance(ca, datetime):
            key = ca.strftime('%Y-%m')
            monthly_new[key] += 1
            if earliest is None or key < earliest:
                earliest = key

    # ── month axis ──
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
        has_data=(treatment_count > 0 or new_patients > 0),
        symbol=symbol,
        mixed_currency=mixed_currency,
        kpis=kpis,
        charts=charts,
    )

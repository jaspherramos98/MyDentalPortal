# File: MyDentalPortal/blueprints/repositories/__init__.py
# Thin data-access layer. Each module wraps one collection's mongo.db queries
# and returns plain dicts (no ORM, no behaviour change for callers).
#
# Why this exists: routes used to query mongo.db directly and re-implement the
# same access-control check in several places. Centralising reads/writes here
# gives multi-staff/audit-log/pricing work a single seam to change. The
# membership-based access swap landed here: patients.get_for_accessor +
# clinics.accessible_ids resolve "who can touch this?" via memberships, so routes
# never re-implement it.

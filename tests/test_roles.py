"""Phase 4: account lifecycle gate at login + role_required foundation."""
from blueprints.routes.auth import account_block_reason


# ── account_block_reason (login lifecycle gate) ─────────────────────────────
def test_approved_active_user_allowed():
    assert account_block_reason({"status": "approved", "is_active": True}) is None


def test_legacy_user_grandfathered():
    # No status / no is_active (pre-feature accounts) -> allowed.
    assert account_block_reason({}) is None


def test_pending_blocked():
    cat, msg = account_block_reason({"status": "pending"})
    assert cat == "warning" and "approval" in msg.lower()


def test_rejected_blocked():
    assert account_block_reason({"status": "rejected"})[0] == "error"


def test_deactivated_blocked_even_if_approved():
    cat, msg = account_block_reason({"status": "approved", "is_active": False})
    assert cat == "error" and "deactivated" in msg.lower()


def test_unknown_status_blocked_by_default():
    # An unexpected lifecycle state (e.g. suspended) must NOT slip through.
    assert account_block_reason({"status": "suspended"}) is not None


# ── role_required decorator ─────────────────────────────────────────────────
def test_role_required_allows_matching_role(client, login):
    login(role="dentist")
    assert client.get("/_dentist_guarded").status_code == 200


def test_role_required_forbids_other_role(client, login):
    login(role="staff")
    assert client.get("/_dentist_guarded").status_code == 403


def test_role_required_admin_satisfies_any_role(client, login):
    # Admin is a global superset — passes a dentist-only gate.
    login(role="admin")
    assert client.get("/_dentist_guarded").status_code == 200


def test_role_required_redirects_anonymous(client):
    resp = client.get("/_dentist_guarded")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

"""Patient age is derived from the birthday (blueprints/ages.py), not a stale
snapshot typed in at registration."""
import pytest

from blueprints.ages import age_on, display_age, age_to_store

JSON_MODE = {"X-Resilient-Submit": "1"}


@pytest.mark.parametrize("birthday, today, expected", [
    ("2000-06-15", "2026-06-14", 25),      # day before birthday
    ("2000-06-15", "2026-06-15", 26),      # on the birthday
    ("2000-02-29", "2026-02-28", 25),      # leap-day birthday, non-leap year
    ("2000-02-29", "2026-03-01", 26),
    ("2026-11-06", "2026-11-06", 0),       # newborn
    ("2027-01-01", "2026-11-06", None),    # future birthday
    ("1800-01-01", "2026-11-06", None),    # implausible
    ("", "2026-11-06", None),
    (None, "2026-11-06", None),
    ("not-a-date", "2026-11-06", None),
])
def test_age_on(birthday, today, expected):
    assert age_on(birthday, today) == expected


def test_display_age_prefers_birthday_over_stale_stored_age():
    assert display_age({"birthday": "1990-01-01", "age": "30"}, "2026-11-06") == 36


def test_display_age_falls_back_to_stored_age_without_birthday():
    assert display_age({"age": "42"}, "2026-11-06") == "42"
    assert display_age({"age": ""}, "2026-11-06") is None
    assert display_age(None, "2026-11-06") is None


def test_age_to_store_ignores_typed_age_when_birthday_is_valid():
    assert age_to_store("1990-01-01", "99", "2026-11-06") == "36"
    assert age_to_store("", " 42 ", "2026-11-06") == "42"


# ── routes ───────────────────────────────────────────────────────────────────

def _expected(birthday="1990-01-01"):
    """Age the app should show today (clinic timezone), as a string."""
    from blueprints.clock import clinic_today
    return str(age_on(birthday, clinic_today("Asia/Manila")))

def _set_birthday(db, world, birthday, age):
    db.patients.update_one({"_id": world.patient_a},
                           {"$set": {"personal_info.birthday": birthday, "personal_info.age": age}})


def test_detail_and_list_show_the_current_age(real_client, as_user, world, db):
    _set_birthday(db, world, "1990-01-01", "20")            # stale snapshot
    as_user("dentist")
    detail = real_client.get(f"/patients/{world.patient_a}").get_data(as_text=True)
    assert "20 years" not in detail
    assert f"{_expected()} years" in detail
    listing = real_client.get("/patients").get_data(as_text=True)
    assert "20 years old" not in listing


def test_edit_form_prefills_computed_age_and_binds_it(real_client, as_user, world, db):
    _set_birthday(db, world, "1990-01-01", "20")
    as_user("dentist")
    html = real_client.get(f"/patients/{world.patient_a}/edit").get_data(as_text=True)
    assert 'data-age-from="birthday"' in html and 'id="birthday"' in html
    assert 'value="20"' not in html and f'value="{_expected()}"' in html
    assert "js/age-field.js" in html


def test_create_form_binds_age_to_birthdate(real_client, as_user):
    as_user("dentist")
    html = real_client.get("/patients/create").get_data(as_text=True)
    assert 'data-age-from="birthdate"' in html and "js/age-field.js" in html


def test_create_stores_age_computed_from_birthday(real_client, as_user, world, db):
    as_user("dentist")
    res = real_client.post("/patients/create", headers=JSON_MODE, data={
        "clinic_id": str(world.clinic_a), "first_name": "Agecheck", "last_name": "Cruz",
        "birthdate": "1990-01-01", "age": "99", "gender": "F",
        "cell_phone": "09170000000", "privacy_consent": "yes",
    })
    assert res.get_json()["ok"] is True
    stored = db.patients.find_one({"personal_info.first_name": "Agecheck"})["personal_info"]["age"]
    assert stored == _expected()


def test_edit_stores_age_computed_from_birthday(real_client, as_user, world, db):
    as_user("dentist")
    res = real_client.post(f"/patients/{world.patient_a}/edit", headers=JSON_MODE, data={
        "first_name": "Alicemarker", "last_name": "A", "birthday": "1990-01-01", "age": "99",
        "cell_phone": "09170000000",
    })
    assert res.get_json()["ok"] is True
    assert db.patients.find_one({"_id": world.patient_a})["personal_info"]["age"] == _expected()


def test_edit_keeps_typed_age_without_birthday(real_client, as_user, world, db):
    as_user("dentist")
    real_client.post(f"/patients/{world.patient_a}/edit", headers=JSON_MODE, data={
        "first_name": "Alicemarker", "last_name": "A", "birthday": "", "age": "41",
        "cell_phone": "09170000000",
    })
    assert db.patients.find_one({"_id": world.patient_a})["personal_info"]["age"] == "41"

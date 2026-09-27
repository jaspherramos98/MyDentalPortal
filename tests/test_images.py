"""Uploaded-image shrinking (blueprints/utils/images.py) + the upload routes using it."""
import io

from PIL import Image

from blueprints.utils.images import DOCUMENT_MAX_SIDE, PHOTO_MAX_SIDE, shrink_image

GPS_IFD = 0x8825
ORIENTATION = 0x0112


def _jpeg(size=(4000, 3000), orientation=None, gps=False, mode="RGB"):
    img = Image.new(mode, size, "white" if mode != "CMYK" else (0, 0, 0, 0))
    # Noise-free but non-trivial content so JPEG sizes are realistic-ish.
    for x in range(0, size[0], 50):
        img.paste((10, 120, 200) if mode == "RGB" else 128, (x, 0, x + 10, size[1]))
    exif = Image.Exif()
    if orientation:
        exif[ORIENTATION] = orientation
    if gps:
        exif[GPS_IFD] = {1: "N", 2: (14.0, 42.0, 0.0), 3: "E", 4: (120.0, 56.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95, exif=exif.tobytes())
    return buf.getvalue()


def _open(data):
    return Image.open(io.BytesIO(data))


def test_large_photo_is_downscaled_and_smaller():
    original = _jpeg()
    out = shrink_image(original, "jpg", PHOTO_MAX_SIDE)
    img = _open(out)
    assert max(img.size) == PHOTO_MAX_SIDE and img.format == "JPEG"
    assert len(out) < len(original) / 5


def test_document_keeps_more_detail_than_photo():
    out = shrink_image(_jpeg(), "jpeg", DOCUMENT_MAX_SIDE)
    assert max(_open(out).size) == DOCUMENT_MAX_SIDE


def test_small_images_are_never_enlarged():
    out = shrink_image(_jpeg(size=(300, 200)), "jpg", PHOTO_MAX_SIDE)
    assert _open(out).size == (300, 200)


def test_camera_rotation_is_applied_before_metadata_is_dropped():
    # Orientation 6 = "rotate 90° CW to display": a 400x200 sensor image is portrait.
    out = shrink_image(_jpeg(size=(400, 200), orientation=6), "jpg", PHOTO_MAX_SIDE)
    img = _open(out)
    assert img.size == (200, 400)
    assert ORIENTATION not in img.getexif()


def test_gps_location_is_stripped():
    original = _jpeg(size=(400, 300), gps=True)
    assert GPS_IFD in _open(original).getexif()
    assert len(_open(shrink_image(original, "jpg", PHOTO_MAX_SIDE)).getexif()) == 0


def test_png_stays_lossless_png_with_alpha():
    img = Image.new("RGBA", (3000, 1000), (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = _open(shrink_image(buf.getvalue(), "png", DOCUMENT_MAX_SIDE))
    assert out.format == "PNG" and out.mode == "RGBA" and out.size == (2000, 667)


def test_cmyk_jpeg_becomes_browser_safe_rgb():
    out = _open(shrink_image(_jpeg(size=(1000, 800), mode="CMYK"), "jpg", PHOTO_MAX_SIDE))
    assert out.mode == "RGB"


def test_non_images_and_undecodable_pass_through_unchanged():
    pdf = b"%PDF-1.7\n fake pdf body"
    heic = b"\x00\x00\x00\x18ftypheic fake"
    assert shrink_image(pdf, "pdf", DOCUMENT_MAX_SIDE) is pdf
    assert shrink_image(heic, "heic", DOCUMENT_MAX_SIDE) is heic
    corrupt = b"\xff\xd8\xff not really a jpeg"
    assert shrink_image(corrupt, "jpg", PHOTO_MAX_SIDE) is corrupt


# ── through the real upload routes ───────────────────────────────────────────

def _upload(client, url, field, data, name):
    return client.post(url, data={field: (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def _blob(db, file_id):
    chunks = db["fs.chunks"].find({"files_id": file_id}).sort("n", 1)
    return b"".join(c["data"] for c in chunks)


def test_photo_route_stores_shrunk_image(real_client, as_user, world, db):
    as_user("dentist")
    _upload(real_client, f"/patients/{world.patient_a}/photo", "photo",
            _jpeg(gps=True), "phone.jpg")
    file_id = db.patients.find_one({"_id": world.patient_a})["photo_file_id"]
    stored = _open(_blob(db, file_id))
    assert max(stored.size) == PHOTO_MAX_SIDE and len(stored.getexif()) == 0


def test_prescription_route_stores_document_size(real_client, as_user, world, db):
    as_user("staff")
    real_client.post(f"/patients/{world.patient_a}/prescriptions/add",
                     data={"description": "Amoxicillin",
                           "image": (io.BytesIO(_jpeg()), "rx.jpg")},
                     content_type="multipart/form-data")
    rx = db.prescriptions.find_one({"patient_id": world.patient_a})
    assert max(_open(_blob(db, rx["image_file_id"])).size) == DOCUMENT_MAX_SIDE


def test_file_route_records_stored_size_and_leaves_pdfs_alone(real_client, as_user, world, db):
    as_user("dentist")
    _upload(real_client, f"/patients/{world.patient_a}/files/add", "file", _jpeg(), "xray.jpg")
    pdf = b"%PDF-1.4\n" + b"x" * 500
    _upload(real_client, f"/patients/{world.patient_a}/files/add", "file", pdf, "report.pdf")
    image_doc = db.patient_files.find_one({"ext": "jpg"})
    stored = _blob(db, image_doc["file_id"])
    assert image_doc["size"] == len(stored)
    assert max(_open(stored).size) == DOCUMENT_MAX_SIDE
    pdf_doc = db.patient_files.find_one({"ext": "pdf"})
    assert _blob(db, pdf_doc["file_id"]) == pdf


# ── one-off backfill (scripts/shrink_existing_images.py) ─────────────────────

def _backfill_module():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "shrink_existing_images.py"
    spec = importlib.util.spec_from_file_location("shrink_existing_images", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _put(db, data, content_type="image/jpeg"):
    from gridfs import GridFS
    return GridFS(db).put(data, filename="x.jpg", contentType=content_type)


def test_backfill_dry_run_writes_nothing(db):
    backfill = _backfill_module()
    old = _put(db, _jpeg())
    pid = db.patients.insert_one({"photo_file_id": old, "photo_ext": "jpg"}).inserted_id
    report = backfill.shrink_all(db, apply=False)
    assert report["profile photos"]["shrunk"] == 1
    assert db.patients.find_one({"_id": pid})["photo_file_id"] == old
    assert db["fs.files"].count_documents({}) == 1


def test_backfill_apply_repoints_deletes_old_and_is_idempotent(db):
    backfill = _backfill_module()
    old_photo = _put(db, _jpeg(gps=True))
    pid = db.patients.insert_one({"photo_file_id": old_photo, "photo_ext": "jpg"}).inserted_id
    old_file = _put(db, _jpeg())
    fid = db.patient_files.insert_one({"file_id": old_file, "ext": "jpg", "size": 1}).inserted_id
    pdf_blob = _put(db, b"%PDF-1.4 body", "application/pdf")
    db.patient_files.insert_one({"file_id": pdf_blob, "ext": "pdf", "size": 13})
    small = _put(db, shrink_image(_jpeg(size=(300, 200)), "jpg", PHOTO_MAX_SIDE))
    db.prescriptions.insert_one({"image_file_id": small, "image_name": "rx.jpg"})

    report = backfill.shrink_all(db, apply=True)
    assert report["profile photos"]["shrunk"] == 1
    assert report["image attachments"]["shrunk"] == 1
    assert report["prescription images"] == {"seen": 1, "shrunk": 0, "skipped": 1,
                                             "before": 0, "after": 0}

    new_photo = db.patients.find_one({"_id": pid})["photo_file_id"]
    assert new_photo != old_photo
    assert max(_open(_blob(db, new_photo)).size) == PHOTO_MAX_SIDE
    assert db["fs.files"].find_one({"_id": old_photo}) is None        # old blob removed
    file_doc = db.patient_files.find_one({"_id": fid})
    assert file_doc["size"] == len(_blob(db, file_doc["file_id"]))
    assert db["fs.files"].find_one({"_id": pdf_blob}) is not None      # pdf untouched

    again = backfill.shrink_all(db, apply=True)                        # idempotent
    assert all(stats["shrunk"] == 0 for stats in again.values())


def test_backfill_refuses_prod_apply_without_flag():
    import pytest
    backfill = _backfill_module()
    with pytest.raises(SystemExit, match="allow-prod"):
        backfill.main(["whatever.env", "dental_portal_prod", "--apply"])

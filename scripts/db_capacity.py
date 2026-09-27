r"""Read-only storage + capacity report for one database (sizes and counts only).

Prints aggregate NUMBERS — collection sizes, average document sizes, GridFS
totals, records-per-patient ratios — and never a document, field value or the
connection string. Safe to run against production.

Usage:
    python scripts/db_capacity.py [env-file] [database]
    (defaults: .env.atlas-admin, dental_portal_prod)
"""
import re
import sys

from pymongo import MongoClient

MB = 1024 * 1024


def load_uri(env_path):
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("MONGO_URI="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(f"No MONGO_URI in {env_path}")


def cluster_scope(uri):
    return re.sub(r"(mongodb(?:\+srv)?://[^/]+)/[^?]*", r"\1/", uri)


def bson_bytes(coll):
    """(count, total BSON bytes, max doc bytes) computed server-side."""
    rows = list(coll.aggregate([{"$group": {
        "_id": None, "n": {"$sum": 1},
        "bytes": {"$sum": {"$bsonSize": "$$ROOT"}},
        "max": {"$max": {"$bsonSize": "$$ROOT"}},
    }}]))
    return (rows[0]["n"], rows[0]["bytes"], rows[0]["max"]) if rows else (0, 0, 0)


def main():
    env_path = sys.argv[1] if len(sys.argv) > 1 else ".env.atlas-admin"
    db_name = sys.argv[2] if len(sys.argv) > 2 else "dental_portal_prod"
    client = MongoClient(cluster_scope(load_uri(env_path)), serverSelectionTimeoutMS=15000)
    db = client[db_name]

    st = db.command("dbStats")
    print(f"DB {db_name}: dataSize={st['dataSize'] / MB:.2f} MB  "
          f"storageSize={st['storageSize'] / MB:.2f} MB  indexSize={st['indexSize'] / MB:.2f} MB  "
          f"objects={st['objects']}")

    print(f"\n{'collection':<22}{'docs':>8}{'bson MB':>10}{'avg KB':>9}{'max KB':>9}")
    per = {}
    for name in sorted(db.list_collection_names()):
        n, total, biggest = bson_bytes(db[name])
        per[name] = (n, total)
        avg = (total / n / 1024) if n else 0
        print(f"{name:<22}{n:>8}{total / MB:>10.3f}{avg:>9.2f}{biggest / 1024:>9.1f}")

    # GridFS blobs: size distribution by content type (no filenames printed).
    print("\nGridFS by content type:")
    for row in db["fs.files"].aggregate([
        {"$group": {"_id": "$contentType", "n": {"$sum": 1}, "bytes": {"$sum": "$length"},
                    "max": {"$max": "$length"}}},
        {"$sort": {"bytes": -1}},
    ]):
        print(f"  {str(row['_id']):<28}{row['n']:>5} files  {row['bytes'] / MB:>8.2f} MB total  "
              f"avg {row['bytes'] / row['n'] / MB:.2f} MB  max {row['max'] / MB:.2f} MB")

    patients = db.patients.count_documents({})
    active = db.patients.count_documents({"is_active": True})
    print(f"\npatients: {patients} total, {active} active")
    if patients:
        for coll in ("treatment_records", "appointments", "dental_charts", "prescriptions",
                     "patient_files", "audit_log"):
            n = per.get(coll, (0, 0))[0]
            print(f"  {coll:<20} {n / patients:>7.2f} per patient")
        with_photo = db.patients.count_documents({"photo_file_id": {"$exists": True, "$ne": None}})
        print(f"  patients with a photo: {with_photo}")


if __name__ == "__main__":
    main()

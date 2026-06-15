"""Read-only Atlas inventory — lists databases, collections, and doc counts.

Reads MONGO_URI from a given env file (default .env.docker) so credentials are
never hardcoded. Usage:
    python scripts/db_inventory.py [path-to-env-file]
"""
import sys
import re
from pymongo import MongoClient


def load_uri(env_path):
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("MONGO_URI=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    raise SystemExit(f"No active MONGO_URI in {env_path}")


def strip_default_db(uri):
    # Connect at cluster scope (no default db) so list_database_names works.
    return re.sub(r"(mongodb\+srv://[^/]+)/[^?]*", r"\1/", uri)


def main():
    env_path = sys.argv[1] if len(sys.argv) > 1 else ".env.atlas-admin"
    uri = strip_default_db(load_uri(env_path))
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    print(f"Connected via {env_path}\n")

    hide = {"admin", "local", "config"}
    for db_name in sorted(client.list_database_names()):
        if db_name in hide:
            continue
        db = client[db_name]
        colls = db.list_collection_names()
        print(f"DB: {db_name}")
        for c in sorted(colls):
            print(f"    {c:<24} {db[c].estimated_document_count():>8} docs")
        if not colls:
            print("    (empty)")
        print()


if __name__ == "__main__":
    main()

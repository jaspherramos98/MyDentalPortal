"""Drop one or more Atlas databases. DESTRUCTIVE.

Requires an explicit --yes flag AND that you type each database name as an
argument, so a stray run can't nuke anything by accident. Reads MONGO_URI from
.env.docker (cluster-scoped).

Usage:
    python scripts/db_drop.py <db> [<db> ...] --yes
"""
import sys
import re
from pymongo import MongoClient


def load_uri(env_path=".env.atlas-admin"):
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("MONGO_URI=") and not line.startswith("#"):
                return re.sub(
                    r"(mongodb\+srv://[^/]+)/[^?]*", r"\1/",
                    line.split("=", 1)[1].strip(),
                )
    raise SystemExit("No active MONGO_URI in env file")


def main():
    dbs = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--yes" not in sys.argv or not dbs:
        raise SystemExit("Refusing: pass db name(s) AND --yes. "
                         "Usage: db_drop.py <db> [<db> ...] --yes")

    client = MongoClient(load_uri(), serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    present = set(client.list_database_names())

    for name in dbs:
        if name not in present:
            print(f"    {name:<26} not present (already gone) - skipped")
            continue
        client.drop_database(name)
        print(f"    {name:<26} DROPPED")

    print("\nRemaining databases:",
          sorted(d for d in client.list_database_names()
                 if d not in ("admin", "local", "config")))


if __name__ == "__main__":
    main()

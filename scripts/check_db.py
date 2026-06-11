r"""Quick MongoDB connectivity check.

Reads the connection string from the MONGO_URI environment variable, connects,
pings the server, and prints the databases/collections it can see. It never
prints the password. Use it to prove a connection works (local, Atlas, or from
the deployed AWS server) before wiring it into the app.

Usage (PowerShell):
    $env:MONGO_URI = "mongodb+srv://user:pass@cluster.xxxx.mongodb.net/dental_portal?retryWrites=true&w=majority"
    .\venv\Scripts\python.exe scripts\check_db.py
"""

import os
import sys
from urllib.parse import urlsplit

from pymongo import MongoClient
from pymongo.errors import PyMongoError


def _redacted(uri: str) -> str:
    """Show the host but hide username/password for safe printing."""
    try:
        parts = urlsplit(uri)
        host = parts.hostname or "?"
        db = parts.path.lstrip("/") or "(none — defaults to 'test')"
        return f"host={host}  database={db}"
    except Exception:
        return "(unparseable URI)"


def main() -> int:
    uri = os.environ.get("MONGO_URI")
    if not uri:
        print("ERROR: MONGO_URI environment variable is not set.")
        return 2

    print(f"Connecting to: {_redacted(uri)}")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        info = client.server_info()
        print(f"OK  Connected. MongoDB server version: {info.get('version')}")

        db = client.get_default_database()
        if db is not None:
            names = db.list_collection_names()
            print(f"OK  Target database '{db.name}' reachable. "
                  f"Collections: {names if names else '(empty — will be created on first use)'}")
        return 0
    except PyMongoError as exc:
        print(f"FAILED  Could not connect/authenticate:\n  {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

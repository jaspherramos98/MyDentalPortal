"""Test a scoped Atlas user: confirm it can read its OWN db and CANNOT read another.

Password is read from the PW environment variable so it never lands in a file
or the command history. Username/dbs are args.

Usage (Git Bash):
    CLUSTER='your-cluster.xxxxx.mongodb.net' PW='thepassword' \
        python scripts/db_test_user.py <user> <allowed_db> <denied_db>

The cluster host is read from the CLUSTER env var (not hardcoded) so the Atlas
endpoint never lands in a committed/public file. PW is read from the environment
so the password never lands in a file or the command history.
"""
import os
import sys
import urllib.parse
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: db_test_user.py <user> <allowed_db> <denied_db>")
    user, allowed, denied = sys.argv[1], sys.argv[2], sys.argv[3]
    pw = os.environ.get("PW")
    if not pw:
        raise SystemExit("Set the PW environment variable to the user's password.")
    cluster = os.environ.get("CLUSTER")
    if not cluster:
        raise SystemExit("Set the CLUSTER environment variable to the Atlas cluster host "
                         "(e.g. your-cluster.xxxxx.mongodb.net).")

    enc = urllib.parse.quote_plus(pw)
    raw_safe = (pw == enc)
    uri = (f"mongodb+srv://{user}:{enc}@{cluster}/{allowed}"
           f"?retryWrites=true&w=majority&appName=db_test_user")

    print(f"User: {user}")
    print(f"Password needs URL-encoding: {'NO (plain alphanumeric)' if raw_safe else 'YES — encode it in the Render URI!'}")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        print("AUTH: success")
    except PyMongoError as e:
        print(f"AUTH: FAILED -> {e}")
        sys.exit(1)

    try:
        n = client[allowed]["patients"].count_documents({})
        print(f"READ {allowed}.patients: OK ({n} docs)  <- expected")
    except OperationFailure as e:
        print(f"READ {allowed}: DENIED -> {e.details.get('errmsg')}  (scope too tight?)")

    try:
        n = client[denied]["patients"].count_documents({})
        print(f"READ {denied}.patients: ALLOWED ({n} docs)  <- BAD, scope too broad!")
    except OperationFailure:
        print(f"READ {denied}: correctly DENIED  <- expected (least-privilege OK)")


if __name__ == "__main__":
    main()

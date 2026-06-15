"""Copy one Atlas database to a new name (documents + indexes).

Non-destructive: the source DB is left untouched. Refuses to write into a
destination that already holds data unless --force is given. Reads MONGO_URI
from .env.docker (cluster-scoped) so credentials stay out of the command line.

Usage:
    python scripts/db_copy.py <src_db> <dst_db> [--force]
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


def copy_indexes(src_coll, dst_coll):
    made = 0
    for idx in src_coll.list_indexes():
        if idx["name"] == "_id_":
            continue
        keys = list(idx["key"].items())
        opts = {k: v for k, v in idx.items()
                if k not in ("key", "v", "ns", "background")}
        name = opts.pop("name", None)
        dst_coll.create_index(keys, name=name, **opts)
        made += 1
    return made


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    if len(args) != 2:
        raise SystemExit("Usage: db_copy.py <src_db> <dst_db> [--force]")
    src_name, dst_name = args

    client = MongoClient(load_uri(), serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    src, dst = client[src_name], client[dst_name]

    existing = [c for c in dst.list_collection_names()
                if dst[c].estimated_document_count() > 0]
    if existing and not force:
        raise SystemExit(
            f"Destination '{dst_name}' already has data in {existing}. "
            f"Re-run with --force to overwrite."
        )

    print(f"Copying {src_name} -> {dst_name}\n")
    for cname in sorted(src.list_collection_names()):
        s, d = src[cname], dst[cname]
        docs = list(s.find({}))
        if force:
            d.drop()
        if docs:
            d.insert_many(docs, ordered=False)
        n_idx = copy_indexes(s, d)
        print(f"    {cname:<24} {len(docs):>6} docs, {n_idx} index(es)")

    # Verify counts match exactly.
    print("\nVerify (src == dst):")
    ok = True
    for cname in sorted(src.list_collection_names()):
        sc = src[cname].count_documents({})
        dc = dst[cname].count_documents({})
        flag = "OK" if sc == dc else "MISMATCH"
        if sc != dc:
            ok = False
        print(f"    {cname:<24} src={sc:>6}  dst={dc:>6}  {flag}")
    print("\nRESULT:", "all collections match" if ok else "MISMATCH - investigate")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

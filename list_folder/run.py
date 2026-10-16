#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    path = dbx.normalize_path(params.get("path"), allow_root=True)
    limit = dbx.int_param(params, "limit", 100, 1, 500)
    body = {"path": path, "recursive": bool(params.get("recursive")), "limit": limit}
    data = dbx.rpc("files/list_folder", body)
    entries = [dbx.entry(item) for item in data.get("entries", [])]
    while data.get("has_more") and len(entries) < limit:
        data = dbx.rpc("files/list_folder/continue", {"cursor": data["cursor"]})
        entries.extend(dbx.entry(item) for item in data.get("entries", []))
    truncated = len(entries) > limit or bool(data.get("has_more"))
    return {"path": path or "/", "entries": entries[:limit], "truncated": truncated}


if __name__ == "__main__":
    dbx.run(main)

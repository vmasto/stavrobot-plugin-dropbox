#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    data = dbx.rpc("files/get_metadata", {"path": dbx.normalize_path(params.get("path"))})
    out = dbx.entry(data)
    out["id"] = data.get("id")
    if data.get(".tag") == "file":
        out["client_modified"] = data.get("client_modified")
    return out


if __name__ == "__main__":
    dbx.run(main)

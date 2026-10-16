#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    data = dbx.rpc("files/delete_v2", {"path": dbx.normalize_path(params.get("path"))})
    return {"deleted": dbx.entry(data["metadata"])}


if __name__ == "__main__":
    dbx.run(main)

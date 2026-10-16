#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    body = {
        "from_path": dbx.normalize_path(params.get("from_path"), "from_path"),
        "to_path": dbx.normalize_path(params.get("to_path"), "to_path"),
        "autorename": False,
    }
    return dbx.entry(dbx.rpc("files/copy_v2", body)["metadata"])


if __name__ == "__main__":
    dbx.run(main)

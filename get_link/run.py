#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    path = dbx.normalize_path(params.get("path"))
    if params.get("temporary"):
        data = dbx.rpc("files/get_temporary_link", {"path": path})
        # get_temporary_link returns FileMetadata without a .tag.
        return {"url": data["link"], "expires_in_hours": 4, **dbx.entry({".tag": "file", **data["metadata"]})}
    try:
        link = dbx.rpc("sharing/create_shared_link_with_settings", {"path": path})
    except dbx.ApiError as error:
        if not error.summary.startswith("shared_link_already_exists"):
            raise
        links = dbx.rpc("sharing/list_shared_links", {"path": path, "direct_only": True}).get("links", [])
        if not links:
            raise
        link = links[0]
    return {"url": link["url"], "name": link.get("name"), "path": link.get("path_lower")}


if __name__ == "__main__":
    dbx.run(main)

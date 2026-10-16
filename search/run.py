#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    query = params.get("query")
    if not isinstance(query, str) or not query.strip():
        raise dbx.ToolError("query is required.")
    options = {"max_results": dbx.int_param(params, "max_results", 20, 1, 100)}
    if params.get("path"):
        options["path"] = dbx.normalize_path(params["path"])
    if params.get("filename_only"):
        options["filename_only"] = True
    data = dbx.rpc(
        "files/search_v2",
        {"query": query.strip(), "options": options, "match_field_options": {"include_highlights": False}},
    )
    matches = [
        dbx.entry(match["metadata"]["metadata"])
        for match in data.get("matches", [])
        if match.get("metadata", {}).get(".tag") == "metadata"
    ]
    return {"matches": matches, "more": bool(data.get("has_more"))}


if __name__ == "__main__":
    dbx.run(main)

#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402
import json  # noqa: E402


def main(params: dict) -> dict:
    path = dbx.normalize_path(params.get("path"))
    response = dbx.send(
        "POST",
        f"{dbx.CONTENT_URL}/files/download",
        headers=dbx.content_headers({"path": path}),
        stream=True,
    )
    if not response.ok:
        raise dbx.api_error(response)
    metadata = json.loads(response.headers["Dropbox-API-Result"])
    if metadata.get("size", 0) > dbx.MAX_TRANSFER_BYTES:
        response.close()
        size_mb = metadata["size"] / 1024 / 1024
        raise dbx.ToolError(f"{metadata['name']} is {size_mb:.0f} MB, over the 25 MB limit. Use get_link.")
    dbx.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (dbx.OUTPUT_DIR / metadata["name"]).open("wb") as target:
        for chunk in response.iter_content(1024 * 1024):
            target.write(chunk)
    # The download result header carries FileMetadata without a .tag.
    return {"file": metadata["name"], **dbx.entry({".tag": "file", **metadata})}


if __name__ == "__main__":
    dbx.run(main)

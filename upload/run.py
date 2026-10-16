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
    source, text = params.get("file"), params.get("text")
    if bool(source) == (text is not None):
        raise dbx.ToolError("Give exactly one of file or text.")
    if source:
        source = Path(source)
        if not source.is_file():
            raise dbx.ToolError("file was not found.")
        data = source.read_bytes()
    elif isinstance(text, str):
        data = text.encode()
    else:
        raise dbx.ToolError("text must be a string.")
    if len(data) > dbx.MAX_TRANSFER_BYTES:
        raise dbx.ToolError("Upload is over the 25 MB limit.")

    overwrite = bool(params.get("overwrite"))
    arg = {"path": path, "mode": "overwrite" if overwrite else "add", "autorename": not overwrite, "mute": True}
    headers = {**dbx.content_headers(arg), "Content-Type": "application/octet-stream"}
    response = dbx.send("POST", f"{dbx.CONTENT_URL}/files/upload", headers=headers, data=data)
    if not response.ok:
        raise dbx.api_error(response)
    metadata = response.json()
    out = dbx.entry({".tag": "file", **metadata})
    if (metadata.get("path_display") or "").lower() != path.lower():
        out["renamed"] = True
    return out


if __name__ == "__main__":
    dbx.run(main)

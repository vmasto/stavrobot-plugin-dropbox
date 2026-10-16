#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402
from urllib.parse import urlencode  # noqa: E402


def main(params: dict) -> dict:
    key, _ = dbx.app_credentials(dbx.load_config())
    query = urlencode({"client_id": key, "response_type": "code", "token_access_type": "offline"})
    return {
        "url": f"{dbx.AUTHORIZE_URL}?{query}",
        "next": "Open the URL, allow access, then pass the code Dropbox shows to auth_complete.",
    }


if __name__ == "__main__":
    dbx.run(main)

#!/usr/bin/env -S uv run
# /// script
# dependencies = ["requests"]
# ///

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dbx  # noqa: E402


def main(params: dict) -> dict:
    code = params.get("code")
    if not isinstance(code, str) or not code.strip():
        raise dbx.ToolError("code is required.")
    key, secret = dbx.app_credentials(dbx.load_config())
    response = dbx.send(
        "POST",
        dbx.TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code.strip()},
        auth=(key, secret),
    )
    if not response.ok:
        raise dbx.ToolError(
            f"Dropbox refused the code ({dbx.token_error(response)}). "
            "Codes work once and expire fast, run auth_url again."
        )
    body = response.json()
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise dbx.ToolError("Dropbox returned no refresh token, run auth_url again.")
    dbx.save_config({"refresh_token": refresh_token})
    return {"connected": True, "scopes": sorted(body.get("scope", "").split())}


if __name__ == "__main__":
    dbx.run(main)

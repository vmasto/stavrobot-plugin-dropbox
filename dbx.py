"""Shared Dropbox client for the plugin's tools."""

import json
import sys
import time
from pathlib import Path

import requests

PLUGIN_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PLUGIN_ROOT / "config.json"
OUTPUT_DIR = Path("/tmp/dropbox")

AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
API_URL = "https://api.dropboxapi.com/2"
CONTENT_URL = "https://content.dropboxapi.com/2"

# The plugin-runner kills a tool after 30 seconds, so give up a bit earlier
# with a readable error instead.
DEADLINE_SECONDS = 25
TIMEOUT = 20
# The plugin-runner refuses to move more than 25 MB per run.
MAX_TRANSFER_BYTES = 25 * 1024 * 1024

_started = time.monotonic()
session = requests.Session()


class ToolError(Exception):
    pass


class ApiError(ToolError):
    def __init__(self, message: str, summary: str = ""):
        super().__init__(message)
        self.summary = summary


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except FileNotFoundError:
        return {}
    except ValueError:
        raise ToolError("config.json is not valid JSON.")


def save_config(updates: dict) -> None:
    # Read again right before writing so keys set elsewhere, like permissions, survive.
    config = load_config()
    config.update(updates)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def app_credentials(config: dict) -> tuple[str, str]:
    key = str(config.get("app_key") or "").strip()
    secret = str(config.get("app_secret") or "").strip()
    if not key or not secret:
        raise ToolError("Set app_key and app_secret from the Dropbox App Console first.")
    return key, secret


def send(method: str, url: str, **kwargs) -> requests.Response:
    remaining = DEADLINE_SECONDS - (time.monotonic() - _started)
    if remaining < 1:
        raise ToolError("Ran out of time talking to Dropbox, try a smaller request.")
    try:
        return session.request(method, url, timeout=min(TIMEOUT, remaining), **kwargs)
    except requests.Timeout:
        raise ToolError("Dropbox did not respond in time.")
    except requests.RequestException as error:
        raise ToolError(f"Network error talking to Dropbox ({type(error).__name__}).")


_token = None


def access_token() -> str:
    global _token
    if _token:
        return _token
    config = load_config()
    key, secret = app_credentials(config)
    refresh_token = str(config.get("refresh_token") or "").strip()
    if not refresh_token:
        raise ToolError("Dropbox is not connected yet. Run auth_url, then auth_complete.")
    response = send(
        "POST",
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(key, secret),
    )
    if not response.ok:
        raise ToolError(
            f"Dropbox refused the refresh token ({token_error(response)}). Run auth_url and auth_complete again."
        )
    _token = response.json()["access_token"]
    return _token


def token_error(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    return body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"


def api_error(response: requests.Response) -> ApiError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    # error_summary looks like "path/not_found/.." and is meant for display.
    summary = str(body.get("error_summary") or "").rstrip("./")

    if error.get(".tag") == "missing_scope":
        scope = error.get("required_scope", "?")
        return ApiError(
            f"The Dropbox app is missing the {scope} scope. Enable it under Permissions "
            "in the App Console, then run auth_url and auth_complete again.",
            summary,
        )
    if response.status_code == 401:
        return ApiError("Dropbox rejected the access token. Run auth_url and auth_complete again.", summary)
    if response.status_code == 429:
        retry = response.headers.get("Retry-After", "a few")
        return ApiError(f"Dropbox is rate limiting, retry in {retry} seconds.", summary)
    if response.status_code == 409:
        return ApiError(f"Dropbox error: {summary or 'conflict'}.", summary)
    text = response.text.strip()[:300] if response.text else ""
    return ApiError(f"Dropbox API error {response.status_code}" + (f": {text}" if text else "."), summary)


def rpc(endpoint: str, body: dict | None = None) -> dict:
    response = send(
        "POST",
        f"{API_URL}/{endpoint}",
        headers={"Authorization": f"Bearer {access_token()}"},
        json=body,
    )
    if not response.ok:
        raise api_error(response)
    return response.json() if response.content else {}


def content_headers(arg: dict) -> dict:
    # Dropbox-API-Arg must be ASCII. json.dumps escapes everything else as \uXXXX,
    # which Dropbox accepts, so Greek or emoji file names survive.
    return {
        "Authorization": f"Bearer {access_token()}",
        "Dropbox-API-Arg": json.dumps(arg),
    }


def read_input(value) -> tuple[str, bytes]:
    """Read a file parameter and return its name and bytes."""
    path = Path(value)
    if not path.is_file():
        raise ToolError("file was not found.")
    data = path.read_bytes()
    # The plugin-runner puts input files in OUTPUT_DIR and sends back whatever is
    # left there, so remove the input to keep it from coming back as an output.
    if path.resolve().parent == OUTPUT_DIR.resolve():
        path.unlink()
    return path.name, data


def normalize_path(value, name: str = "path", allow_root: bool = False) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_root:
            return ""
        raise ToolError(f"{name} is required.")
    if not isinstance(value, str):
        raise ToolError(f"{name} must be a string.")
    path = value.strip()
    if path.startswith(("id:", "rev:", "ns:")):
        return path
    if path == "/":
        if allow_root:
            return ""
        raise ToolError(f"{name} can't be the Dropbox root.")
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


def entry(metadata: dict) -> dict:
    tag = metadata.get(".tag")
    out = {"type": tag, "name": metadata.get("name"), "path": metadata.get("path_display")}
    if tag == "file":
        out["size"] = metadata.get("size")
        out["modified"] = metadata.get("server_modified")
    return out


def int_param(params: dict, name: str, default: int, low: int, high: int) -> int:
    value = params.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{name} must be a whole number.")
    return max(low, min(high, value))


def run(main) -> None:
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
        if not isinstance(params, dict):
            raise ToolError("Input must be a JSON object.")
        result = main(params)
    except ToolError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Input is not valid JSON.", file=sys.stderr)
        sys.exit(1)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

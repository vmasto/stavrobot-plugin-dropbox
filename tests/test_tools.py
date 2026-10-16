"""Offline tests against a fake Dropbox.

Run with: uv run --with pytest --with requests pytest tests
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dbx  # noqa: E402


class Response:
    def __init__(self, status=200, body=None, headers=None, content=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.headers = headers or {}
        self.content = content if content is not None else (b"" if body is None else json.dumps(body).encode())
        self.text = self.content.decode(errors="replace")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def iter_content(self, size):
        yield self.content

    def close(self):
        pass


@pytest.fixture
def fake(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"app_key": "key", "app_secret": "secret", "refresh_token": "rt", "permissions": ["*"]})
    )
    monkeypatch.setattr(dbx, "CONFIG_PATH", config)
    monkeypatch.setattr(dbx, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(dbx, "_token", None)

    calls = []
    routes = {}

    def request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        assert 0 < kwargs["timeout"] <= dbx.TIMEOUT
        if url == dbx.TOKEN_URL and kwargs["data"]["grant_type"] == "refresh_token":
            return Response(200, {"access_token": "at"})
        handler = routes[url.rsplit("/2/", 1)[-1] if "/2/" in url else url]
        return handler(kwargs) if callable(handler) else handler

    monkeypatch.setattr(dbx.session, "request", request)
    return type("Fake", (), {"routes": routes, "calls": calls, "config": config})


def tool(name):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", ROOT / name / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def body_of(call):
    return call["json"]


def test_normalize_path():
    assert dbx.normalize_path(None, allow_root=True) == ""
    assert dbx.normalize_path("/", allow_root=True) == ""
    assert dbx.normalize_path("Photos/") == "/Photos"
    assert dbx.normalize_path("id:abc") == "id:abc"
    with pytest.raises(dbx.ToolError):
        dbx.normalize_path("/")
    with pytest.raises(dbx.ToolError):
        dbx.normalize_path("")


def test_auth_url_asks_for_offline_access(fake):
    out = tool("auth_url")({})
    assert out["url"].startswith(dbx.AUTHORIZE_URL)
    assert "client_id=key" in out["url"] and "token_access_type=offline" in out["url"]


def test_auth_complete_saves_token_and_keeps_other_keys(fake):
    fake.routes[dbx.TOKEN_URL] = Response(
        200, {"refresh_token": "new", "scope": "files.content.read account_info.read"}
    )
    out = tool("auth_complete")({"code": " abc "})
    assert out == {"connected": True, "scopes": ["account_info.read", "files.content.read"]}
    saved = json.loads(fake.config.read_text())
    assert saved["refresh_token"] == "new" and saved["permissions"] == ["*"]
    assert fake.calls[0]["data"] == {"grant_type": "authorization_code", "code": "abc"}
    assert fake.calls[0]["auth"] == ("key", "secret")


def test_auth_complete_reports_bad_code(fake):
    fake.routes[dbx.TOKEN_URL] = Response(400, {"error": "invalid_grant", "error_description": "code doesn't exist"})
    with pytest.raises(dbx.ToolError, match="code doesn't exist"):
        tool("auth_complete")({"code": "abc"})


def test_missing_refresh_token(fake):
    fake.config.write_text(json.dumps({"app_key": "key", "app_secret": "secret"}))
    with pytest.raises(dbx.ToolError, match="auth_url"):
        tool("list_folder")({})


def file_entry(name, size=10):
    return {
        ".tag": "file",
        "name": name,
        "path_display": f"/{name}",
        "size": size,
        "server_modified": "2026-10-16T10:00:00Z",
    }


def test_list_folder_pages_and_truncates(fake):
    fake.routes["files/list_folder"] = Response(
        200, {"entries": [file_entry("a"), file_entry("b")], "has_more": True, "cursor": "c1"}
    )
    fake.routes["files/list_folder/continue"] = Response(
        200, {"entries": [file_entry("c")], "has_more": True, "cursor": "c2"}
    )
    out = tool("list_folder")({"path": "/", "limit": 2})
    assert out["path"] == "/" and [e["name"] for e in out["entries"]] == ["a", "b"] and out["truncated"]
    assert body_of(fake.calls[1])["path"] == ""

    fake.calls.clear()
    out = tool("list_folder")({"limit": 3})
    assert [e["name"] for e in out["entries"]] == ["a", "b", "c"] and out["truncated"]


def test_search_unwraps_metadata(fake):
    fake.routes["files/search_v2"] = Response(
        200, {"matches": [{"metadata": {".tag": "metadata", "metadata": file_entry("tax.pdf")}}], "has_more": False}
    )
    out = tool("search")({"query": "tax", "path": "Documents", "filename_only": True})
    assert out == {"matches": [dbx.entry(file_entry("tax.pdf"))], "more": False}
    options = body_of(fake.calls[-1])["options"]
    assert options == {"max_results": 20, "path": "/Documents", "filename_only": True}


def test_download_writes_attachment(fake):
    # The real header has no .tag.
    meta = {key: value for key, value in file_entry("Σημειώσεις.txt", 5).items() if key != ".tag"}
    fake.routes["files/download"] = Response(200, headers={"Dropbox-API-Result": json.dumps(meta)}, content=b"hello")
    out = tool("download")({"path": "/Σημειώσεις.txt"})
    assert out["file"] == "Σημειώσεις.txt" and out["type"] == "file" and out["size"] == 5
    assert (dbx.OUTPUT_DIR / "Σημειώσεις.txt").read_bytes() == b"hello"
    header = fake.calls[-1]["headers"]["Dropbox-API-Arg"]
    assert header.isascii() and json.loads(header) == {"path": "/Σημειώσεις.txt"}


def test_download_refuses_big_files(fake):
    meta = file_entry("video.mp4", dbx.MAX_TRANSFER_BYTES + 1)
    fake.routes["files/download"] = Response(200, headers={"Dropbox-API-Result": json.dumps(meta)}, content=b"")
    with pytest.raises(dbx.ToolError, match="get_link"):
        tool("download")({"path": "/video.mp4"})


def test_upload_text_without_overwrite_autorenames(fake):
    fake.routes["files/upload"] = Response(200, file_entry("notes (1).txt", 2))
    out = tool("upload")({"path": "/notes.txt", "text": "hi"})
    assert out["renamed"] and out["path"] == "/notes (1).txt"
    call = fake.calls[-1]
    assert call["data"] == b"hi"
    assert json.loads(call["headers"]["Dropbox-API-Arg"]) == {
        "path": "/notes.txt",
        "mode": "add",
        "autorename": True,
        "mute": True,
    }


def test_upload_file_with_overwrite(fake, tmp_path):
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"jpg")
    fake.routes["files/upload"] = Response(200, file_entry("photo.jpg", 3))
    out = tool("upload")({"path": "/photo.jpg", "file": str(source), "overwrite": True})
    assert "renamed" not in out
    assert json.loads(fake.calls[-1]["headers"]["Dropbox-API-Arg"])["mode"] == "overwrite"


def test_upload_needs_exactly_one_source(fake):
    with pytest.raises(dbx.ToolError, match="exactly one"):
        tool("upload")({"path": "/a.txt"})
    with pytest.raises(dbx.ToolError, match="exactly one"):
        tool("upload")({"path": "/a.txt", "text": "x", "file": "/tmp/x"})


def test_create_move_copy_delete(fake):
    fake.routes["files/create_folder_v2"] = Response(200, {"metadata": {"name": "New", "path_display": "/New"}})
    assert tool("create_folder")({"path": "/New"}) == {"type": "folder", "name": "New", "path": "/New"}
    fake.routes["files/move_v2"] = Response(200, {"metadata": file_entry("b")})
    assert tool("move")({"from_path": "/a", "to_path": "/b"})["path"] == "/b"
    assert body_of(fake.calls[-1]) == {"from_path": "/a", "to_path": "/b", "autorename": False}
    fake.routes["files/copy_v2"] = Response(200, {"metadata": file_entry("c")})
    assert tool("copy")({"from_path": "/a", "to_path": "/c"})["path"] == "/c"
    fake.routes["files/delete_v2"] = Response(200, {"metadata": file_entry("a")})
    assert tool("delete")({"path": "/a"}) == {"deleted": dbx.entry(file_entry("a"))}


def test_conflict_errors_use_the_summary(fake):
    fake.routes["files/move_v2"] = Response(409, {"error_summary": "to/conflict/file/..", "error": {".tag": "to"}})
    with pytest.raises(dbx.ToolError, match="to/conflict/file"):
        tool("move")({"from_path": "/a", "to_path": "/b"})


def test_missing_scope_explains_the_fix(fake):
    fake.routes["files/delete_v2"] = Response(
        401,
        {
            "error_summary": "missing_scope/",
            "error": {".tag": "missing_scope", "required_scope": "files.content.write"},
        },
    )
    with pytest.raises(dbx.ToolError, match="files.content.write scope"):
        tool("delete")({"path": "/a"})


def test_get_link_reuses_an_existing_link(fake):
    fake.routes["sharing/create_shared_link_with_settings"] = Response(
        409, {"error_summary": "shared_link_already_exists/metadata/..", "error": {}}
    )
    fake.routes["sharing/list_shared_links"] = Response(
        200, {"links": [{"url": "https://www.dropbox.com/s/x", "name": "a.pdf", "path_lower": "/a.pdf"}]}
    )
    assert tool("get_link")({"path": "/a.pdf"}) == {
        "url": "https://www.dropbox.com/s/x",
        "name": "a.pdf",
        "path": "/a.pdf",
    }


def test_get_link_temporary(fake):
    fake.routes["files/get_temporary_link"] = Response(
        200,
        {
            "link": "https://dl.dropboxusercontent.com/x",
            "metadata": {"name": "a.pdf", "path_display": "/a.pdf", "size": 3},
        },
    )
    out = tool("get_link")({"path": "/a.pdf", "temporary": True})
    assert out["url"].startswith("https://dl.") and out["expires_in_hours"] == 4
    assert out["type"] == "file" and out["size"] == 3


def test_errors_exit_non_zero_with_stderr(tmp_path):
    # No config.json next to the copied tool, so it must fail before any network call.
    plugin = tmp_path / "dropbox"
    (plugin / "list_folder").mkdir(parents=True)
    (plugin / "dbx.py").write_text((ROOT / "dbx.py").read_text())
    (plugin / "list_folder" / "run.py").write_text((ROOT / "list_folder" / "run.py").read_text())
    result = subprocess.run(
        [sys.executable, str(plugin / "list_folder" / "run.py")],
        input="{}",
        capture_output=True,
        text=True,
        cwd=plugin / "list_folder",
    )
    assert result.returncode == 1 and result.stdout == ""
    assert "app_key" in result.stderr


def test_run_scripts_are_executable_in_git():
    output = subprocess.run(
        ["git", "ls-files", "-s", "--", "*/run.py"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    entries = [line.split(maxsplit=3) for line in output.splitlines()]
    if not entries:
        pytest.skip("run.py files are not in the git index yet")
    assert all(mode == "100755" for mode, *_ in entries), entries

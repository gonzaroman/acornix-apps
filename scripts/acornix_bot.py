"""Shared helpers for the GitHub Actions that review and publish apps sent from Acornix.

A submission is an issue opened by Acornix on behalf of its author. The issue body carries a
marker, the app's details as JSON and the id of a gist with the app's files:

    index.html (and any other text files of the app)
    screenshot.jpg.b64   the screenshot, base64-encoded (gists only hold text)

Everything in the issue and the gist is untrusted: it's only ever read as data, never run.
"""
import base64
import binascii
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_catalog  # noqa: E402

API = "https://api.github.com"
MARKER = "<!-- acornix-submission v1 -->"
REVIEW_MARKER = re.compile(r"<!-- acornix-review (\{.*?\}) -->")
DATA_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TEXT_FILE = re.compile(r"\.(html?|js|mjs|css|json|svg|txt|md)$", re.IGNORECASE)
SCREENSHOT = "screenshot.jpg.b64"
MAX_SCREENSHOT_BYTES = 1024 * 1024
LIMITS = {"name": 40, "emoji": 16, "description": 300, "prompt": 2000}


class Rejected(Exception):
    """The submission can't be accepted as it is; the message is shown to the author."""


def event():
    return json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))


def github(method, path, body=None, raw=False):
    url = path if path.startswith("http") else API + path
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "acornix-apps-bot",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = resp.read()
    if raw:
        return payload
    return json.loads(payload) if payload else None


def repo():
    return os.environ["GITHUB_REPOSITORY"]


def comment(issue, text):
    github("POST", f"/repos/{repo()}/issues/{issue}/comments", {"body": text})


def set_labels(issue, add=(), remove=()):
    for name in remove:
        try:
            github("DELETE", f"/repos/{repo()}/issues/{issue}/labels/{urllib.request.quote(name)}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    if add:
        github("POST", f"/repos/{repo()}/issues/{issue}/labels", {"labels": list(add)})


def close(issue, reason="completed"):
    github("PATCH", f"/repos/{repo()}/issues/{issue}", {"state": "closed", "state_reason": reason})


def parse_submission(body):
    """The app's details from the issue body, checked and trimmed."""
    if MARKER not in (body or ""):
        return None
    match = DATA_BLOCK.search(body)
    if not match:
        raise Rejected("The submission data is missing. Please publish again from Acornix.")
    try:
        data = json.loads(match.group(1))
    except ValueError:
        raise Rejected("The submission data is not valid JSON. Please publish again from Acornix.")
    sub = {k: str(data.get(k, "")).strip() for k in ("id", "name", "emoji", "category", "description", "prompt", "language", "gist")}
    if not build_catalog.ID.match(sub["id"]) or len(sub["id"]) > 40:
        raise Rejected("The app id must be lowercase letters, numbers and dashes.")
    if any(ord(c) < 32 for k in ("name", "emoji", "category") for c in sub[k]):
        raise Rejected("The name, emoji and category must be a single line.")
    if not sub["name"] or not sub["description"]:
        raise Rejected("The app needs a name and a description.")
    for field, limit in LIMITS.items():
        if len(sub[field]) > limit:
            raise Rejected(f"The {field} is too long (at most {limit} characters).")
    if sub["category"] not in build_catalog.CATEGORIES:
        raise Rejected(f"The category must be one of: {', '.join(sorted(build_catalog.CATEGORIES))}.")
    if not re.fullmatch(r"[0-9a-f]{20,40}", sub["gist"]):
        raise Rejected("The gist id is not valid.")
    sub["emoji"] = sub["emoji"] or "🌰"
    sub["language"] = sub["language"][:8] or "en"
    return sub


def fetch_gist(gist_id, revision=None):
    """(owner, revision, {name: text}) of a gist, at a given revision or the latest one."""
    gist = github("GET", f"/gists/{gist_id}" + (f"/{revision}" if revision else ""))
    files = {}
    for name, info in (gist.get("files") or {}).items():
        content = info.get("content")
        if info.get("truncated") or content is None:
            content = github("GET", info["raw_url"], raw=True).decode("utf-8", errors="replace")
        files[name] = content
    owner = (gist.get("owner") or {}).get("login", "")
    version = revision or (gist.get("history") or [{}])[0].get("version", "")
    return owner, version, files


def split_files(files):
    """The app's own files and the decoded screenshot, after checking names and sizes."""
    if "index.html" not in files:
        raise Rejected("The gist has no index.html.")
    if SCREENSHOT not in files:
        raise Rejected("The gist has no screenshot.")
    try:
        shot = base64.b64decode(files[SCREENSHOT], validate=False)
    except (binascii.Error, ValueError):
        raise Rejected("The screenshot is not valid base64.")
    if not shot.startswith(b"\xff\xd8") or len(shot) > MAX_SCREENSHOT_BYTES:
        raise Rejected("The screenshot must be a JPEG of 1 MB at most.")
    app = {}
    for name, text in files.items():
        if name == SCREENSHOT:
            continue
        if not FILE_NAME.match(name) or not TEXT_FILE.search(name) or name in ("app.json", "screenshot.jpg"):
            raise Rejected(f"The gist has a file that can't be published: {name}")
        app[name] = text
    size = sum(len(t.encode("utf-8")) for t in app.values())
    if size > build_catalog.MAX_APP_BYTES:
        raise Rejected(f"The app is {size // 1024} KB; the limit is {build_catalog.MAX_APP_BYTES // 1024} KB.")
    return app, shot


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def existing(app_id):
    path = ROOT / "apps" / app_id / "app.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

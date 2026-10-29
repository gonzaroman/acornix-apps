#!/usr/bin/env python3
"""Download counts for the gallery, with no server: GitHub counts them for us.

Every app is also kept as apps/<id>.zip in the release tagged "apps", and Acornix installs from
there, so GitHub's download_count of that file says how many times it was installed or tried.
stats/downloads.json keeps those counts (and a short daily history for "trending"), and
build_catalog.py copies them into catalog.json.

    python3 scripts/downloads.py upload <id> [<id> ...]   zip apps/<id>/ and put it in the release
    python3 scripts/downloads.py refresh                  read today's counts from GitHub

Replacing a ZIP (a new version of an app) resets GitHub's counter, so the count it had is added
to the app's "base" first and nothing is lost.
"""
import datetime
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "stats" / "downloads.json"
TAG = "apps"
REPO = os.environ.get("GITHUB_REPOSITORY", "gonzaroman/acornix-apps")
HISTORY_DAYS = 35
NOT_IN_ZIP = {"app.json", "screenshot.jpg"}


def token():
    return os.environ.get("GITHUB_TOKEN") or subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def api(method, url, body=None, content_type="application/json"):
    if not url.startswith("http"):
        url = f"https://api.github.com/repos/{REPO}{url}"
    data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": content_type,
        "User-Agent": "acornix-apps-bot",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
    return json.loads(payload) if payload else None


def load():
    if STATS.exists():
        return json.loads(STATS.read_text(encoding="utf-8"))
    return {"assets": {}, "history": {}}


def save(stats):
    STATS.parent.mkdir(exist_ok=True)
    STATS.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def release():
    return api("GET", f"/releases/tags/{TAG}")


def zip_app(app_id):
    folder = ROOT / "apps" / app_id
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name not in NOT_IN_ZIP:
                z.write(path, path.relative_to(folder).as_posix())
    return out.getvalue()


def upload(app_ids):
    stats = load()
    rel = release()
    assets = {a["name"]: a for a in rel["assets"]}
    for app_id in app_ids:
        entry = stats["assets"].setdefault(app_id, {"base": 0, "count": 0, "asset": 0})
        old = assets.get(f"{app_id}.zip")
        if old:
            entry["base"] += old["download_count"]
            api("DELETE", f"/releases/assets/{old['id']}")
        url = rel["upload_url"].split("{")[0] + f"?name={app_id}.zip"
        new = api("POST", url, zip_app(app_id), content_type="application/zip")
        entry.update(count=0, asset=new["id"])
        print(f"{app_id}.zip uploaded")
    save(stats)


def refresh():
    stats = load()
    for asset in release()["assets"]:
        app_id = asset["name"].removesuffix(".zip")
        if not (ROOT / "apps" / app_id).is_dir():
            continue
        entry = stats["assets"].setdefault(app_id, {"base": 0, "count": 0, "asset": asset["id"]})
        if entry["asset"] != asset["id"]:
            # Replaced by hand: keep what the old file had counted.
            entry["base"] += entry["count"]
            entry["asset"] = asset["id"]
        entry["count"] = asset["download_count"]
    today = datetime.date.today()
    stats["history"][today.isoformat()] = {k: v["base"] + v["count"] for k, v in sorted(stats["assets"].items())}
    oldest = (today - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    stats["history"] = {d: v for d, v in stats["history"].items() if d >= oldest}
    save(stats)
    print(f"{len(stats['assets'])} apps counted")


if __name__ == "__main__":
    if sys.argv[1:2] == ["upload"] and sys.argv[2:]:
        upload(sys.argv[2:])
    elif sys.argv[1:] == ["refresh"]:
        refresh()
    else:
        print(__doc__)
        sys.exit(2)

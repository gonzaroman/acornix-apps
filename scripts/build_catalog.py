#!/usr/bin/env python3
"""Checks every app in apps/ and writes catalog.json, the file Acornix reads to show the gallery.

Usage: python3 scripts/build_catalog.py [--check]
With --check it only validates and fails if catalog.json is out of date.
"""
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"
CATALOG = ROOT / "catalog.json"
STATS = ROOT / "stats" / "downloads.json"
TREND_DAYS = 7

# The App Store's categories, without the ones that don't fit apps made in Acornix
# (social networks, news, magazines, books, medical, navigation, developer tools).
CATEGORIES = {
    "games", "entertainment", "utilities", "productivity", "finance", "business", "education",
    "reference", "health-fitness", "sports", "music", "photo-video", "graphics-design", "lifestyle",
    "food-drink", "travel", "kids", "shopping", "weather",
}
REQUIRED = ["id", "name", "emoji", "category", "description", "author", "version", "added", "updated"]
MAX_APP_BYTES = 2 * 1024 * 1024
ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# What the code uses, shown as labels so people know before installing.
TAGS = {
    "ai": re.compile(r"\baskAI\b|\bai\.chat\b"),
    "phone": re.compile(r"Acornix\.(speak|flashlight|notify|battery|deviceInfo|listApps|openApp)\b"),
    "camera": re.compile(r"getUserMedia\s*\(\s*\{[^}]*video|\bcapture\s*=|facingMode"),
    "microphone": re.compile(r"getUserMedia\s*\(\s*\{[^}]*audio|SpeechRecognition"),
    "internet": re.compile(r"<script[^>]+src=[\"']https?://|import\s[^;]*from\s+[\"']https?://|fetch\s*\(\s*[\"'`]https?://"),
}


def download_counts():
    """{id: (all-time downloads, downloads in the last week of the history)} from stats/downloads.json."""
    if not STATS.exists():
        return {}
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    totals = {k: v["base"] + v["count"] for k, v in stats.get("assets", {}).items()}
    days = sorted(stats.get("history", {}))
    if not days:
        return {k: (n, 0) for k, n in totals.items()}
    # A week before the newest day counted (or the oldest day there is), so the result doesn't depend on today.
    latest = datetime.date.fromisoformat(days[-1])
    start = max([d for d in days if d <= (latest - datetime.timedelta(days=TREND_DAYS)).isoformat()] or [days[0]])
    before = stats["history"][start]
    return {k: (n, max(0, n - before.get(k, 0))) for k, n in totals.items()}


def build():
    counts = download_counts()
    errors, apps = [], []
    for folder in sorted(p for p in APPS.iterdir() if p.is_dir()):
        where = f"apps/{folder.name}"
        try:
            meta = json.loads((folder / "app.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            errors.append(f"{where}: app.json is missing or invalid ({e})")
            continue
        missing = [k for k in REQUIRED if meta.get(k) in (None, "")]
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}")
            continue
        if meta["id"] != folder.name or not ID.match(meta["id"]):
            errors.append(f"{where}: id must be the folder name, in lowercase-with-dashes")
        if meta["category"] not in CATEGORIES:
            errors.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        if not DATE.match(meta["added"]) or not DATE.match(meta["updated"]):
            errors.append(f"{where}: dates must be YYYY-MM-DD")
        index = folder / "index.html"
        if not index.is_file():
            errors.append(f"{where}: index.html is missing")
            continue
        if not (folder / "screenshot.jpg").is_file():
            errors.append(f"{where}: screenshot.jpg is missing")
        files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                       if p.is_file() and p.name not in ("app.json", "screenshot.jpg"))
        size = sum((folder / f).stat().st_size for f in files)
        if size > MAX_APP_BYTES:
            errors.append(f"{where}: the app is {size} bytes, the limit is {MAX_APP_BYTES}")
        code = index.read_text(encoding="utf-8", errors="replace")
        apps.append({
            "id": meta["id"],
            "name": meta["name"].strip(),
            "emoji": meta["emoji"],
            "category": meta["category"],
            "description": meta["description"].strip(),
            "prompt": meta.get("prompt", "").strip(),
            "author": meta["author"],
            "language": meta.get("language", "en"),
            "version": int(meta["version"]),
            "added": meta["added"],
            "updated": meta["updated"],
            "featured": bool(meta.get("featured", False)),
            "tags": [t for t, rx in TAGS.items() if rx.search(code)],
            "files": files,
            "size": size,
            "sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
            "downloads": counts.get(meta["id"], (0, 0))[0],
            "trending": counts.get(meta["id"], (0, 0))[1],
        })
    # Newest first; Acornix sorts and filters on its side too.
    apps.sort(key=lambda a: (a["added"], a["featured"], a["name"]), reverse=True)
    return errors, {"version": 1, "apps": apps}


def main():
    errors, catalog = build()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        if not CATALOG.exists() or CATALOG.read_text(encoding="utf-8") != text:
            print("catalog.json is out of date: run python3 scripts/build_catalog.py", file=sys.stderr)
            sys.exit(1)
        print(f"OK: {len(catalog['apps'])} apps")
        return
    CATALOG.write_text(text, encoding="utf-8")
    print(f"catalog.json: {len(catalog['apps'])} apps")


if __name__ == "__main__":
    main()

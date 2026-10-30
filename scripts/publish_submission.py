#!/usr/bin/env python3
"""Publishes a reviewed app when a maintainer labels its issue "approved".

It takes the gist at the exact revision that was reviewed (so later edits to the gist don't get
in), writes apps/<id>/, rebuilds catalog.json and leaves the commit to the workflow.
"""
import datetime
import json
import shutil
import sys

from acornix_bot import (
    REVIEW_MARKER, ROOT, Rejected, close, comment, event, existing, fetch_gist, github, parse_submission,
    repo, set_labels, sha256, split_files,
)
import build_catalog
import downloads


def last_review(number):
    """The data of the newest review comment written by the bot."""
    comments = github("GET", f"/repos/{repo()}/issues/{number}/comments?per_page=100")
    for c in reversed(comments):
        if c["user"]["login"] != "github-actions[bot]":
            continue
        match = REVIEW_MARKER.search(c.get("body") or "")
        if match:
            return json.loads(match.group(1))
    return None


def main():
    issue = event()["issue"]
    number, author = issue["number"], issue["user"]["login"]
    try:
        sub = parse_submission(issue.get("body"))
        review = last_review(number)
        if sub is None or review is None:
            raise Rejected("There's no review to publish. Run the review first.")
        if review["id"] != sub["id"] or review["gist"] != sub["gist"]:
            raise Rejected("The submission changed after it was reviewed. Run the review again.")
        _, _, files = fetch_gist(sub["gist"], review["revision"])
        app, shot = split_files(files)
        if sha256(app["index.html"]) != review["sha256"]:
            raise Rejected("The code doesn't match the reviewed version.")
        current = existing(sub["id"])
        if current and current["author"].lower() != author.lower():
            raise Rejected("Another author published an app with this id in the meantime.")
    except Rejected as e:
        comment(number, f"⚠️ Not published: {e}")
        set_labels(number, remove=["approved"])
        raise SystemExit(1)

    today = datetime.date.today().isoformat()
    folder = ROOT / "apps" / sub["id"]
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for name, text in app.items():
        (folder / name).write_text(text, encoding="utf-8")
    (folder / "screenshot.jpg").write_bytes(shot)
    meta = {
        "id": sub["id"],
        "name": sub["name"],
        "emoji": sub["emoji"],
        "category": sub["category"],
        "description": sub["description"],
        **({"description_i18n": sub["description_i18n"]} if sub.get("description_i18n") else {}),
        "prompt": sub["prompt"],
        "author": author,
        "language": sub["language"],
        "version": current["version"] + 1 if current else 1,
        "added": current["added"] if current else today,
        "updated": today,
        "featured": bool(current and current.get("featured")),
        "issue": number,
    }
    (folder / "app.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Acornix installs from the ZIP in the "apps" release, which is how downloads are counted.
    downloads.upload([sub["id"]])
    errors, catalog = build_catalog.build()
    if errors:
        comment(number, "⚠️ Not published, the catalog check failed:\n\n" + "\n".join(f"- {e}" for e in errors))
        raise SystemExit(1)
    build_catalog.CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # The workflow commits with this message, then runs --announce.
    print(f"Publish {sub['name']} by @{author} (#{number})")


def announce():
    """After the commit is pushed: thank the author and close the issue."""
    issue = event()["issue"]
    sub = parse_submission(issue.get("body"))
    meta = existing(sub["id"])
    what = f"version {meta['version']}" if meta["version"] > 1 else "it"
    comment(issue["number"], f"## 🎉 Published\n\n{sub['emoji']} **{sub['name']}** is in the gallery: open Acornix › Community apps. "
                             f"Thanks for sharing {what}, @{issue['user']['login']}!")
    set_labels(issue["number"], add=["published"])
    close(issue["number"])


if __name__ == "__main__":
    announce() if "--announce" in sys.argv else main()

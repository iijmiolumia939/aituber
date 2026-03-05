#!/usr/bin/env python3
"""Fetch issue bodies."""
import json
import sys
import urllib.request

TOKEN = "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"
REPO = "iijmiolumia939/aituber"
BASE = f"https://api.github.com/repos/{REPO}"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "aituber-agent/1.0",
}


def api(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def close_issue(n, comment):
    api("POST", f"/issues/{n}/comments", {"body": comment})
    api("PATCH", f"/issues/{n}", {"state": "closed"})
    print(f"Closed #{n}", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"

    if mode == "close":
        for n in [int(x) for x in sys.argv[2:]]:
            close_issue(n, "実装完了。コミット `32dc81e` で merge 済み。")

    elif mode == "detail":
        for n in [int(x) for x in sys.argv[2:]]:
            i = api("GET", f"/issues/{n}")
            print(f"\n### #{i['number']} {i['title']}")
            print(i.get("body", "(no body)"))
            print("---")
            sys.stdout.flush()

    else:
        issues = api("GET", "/issues?state=open&per_page=50")
        for i in sorted(issues, key=lambda x: x["number"]):
            labels = "|".join(l["name"] for l in i["labels"])
            print(f"#{i['number']:3d} [{labels}] {i['title']}")

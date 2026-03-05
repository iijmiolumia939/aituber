#!/usr/bin/env python3
"""Get details for all open issues and optionally close specified ones."""
import json
import sys
import urllib.request

TOKEN = open("scripts/create_embodied_ai_issues.py", encoding="utf-8").read().split('TOKEN  = "')[1].split('"')[0]
REPO = "iijmiolumia939/aituber"
BASE = f"https://api.github.com/repos/{REPO}"
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"}


def api(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=HEADERS, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def get_issue(n):
    return api("GET", f"/issues/{n}")


def close_issue(n, comment):
    api("POST", f"/issues/{n}/comments", {"body": comment})
    api("PATCH", f"/issues/{n}", {"state": "closed"})
    print(f"  Closed #{n}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"

    if mode == "close":
        issue_nums = [int(x) for x in sys.argv[2:]]
        for n in issue_nums:
            close_issue(n, "実装完了。コミット `32dc81e` で merge済み。")
    elif mode == "detail":
        for n in sys.argv[2:]:
            i = get_issue(int(n))
            print(f"\n=== #{i['number']} {i['title']} ===")
            print(i.get("body", ""))
    else:
        issues = api("GET", "/issues?state=open&per_page=50")
        for i in sorted(issues, key=lambda x: x["number"]):
            labels = "|".join(l["name"] for l in i["labels"])
            print(f"#{i['number']:3d} [{labels}] {i['title']}")

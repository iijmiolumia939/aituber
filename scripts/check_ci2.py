"""Check GitHub Actions CI status and get failure details."""
import urllib.request
import json
import os

token = os.environ.get("GITHUB_TOKEN", "")
headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def get(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


runs = get("https://api.github.com/repos/iijmiolumia939/aituber/actions/runs?per_page=5")
for run in runs["workflow_runs"]:
    print(f"#{run['id']} [{run['conclusion'] or run['status']}] {run['name']} sha={run['head_sha'][:8]} {run['created_at']}")

# Detailed failure info for all recent failed runs
for run in runs["workflow_runs"][:3]:
    if run["conclusion"] in ("failure", "startup_failure") or run["status"] == "in_progress":
        print(f"\n--- Jobs for run #{run['id']} ({run['name']}) sha={run['head_sha'][:8]} ---")
        jobs = get(f"https://api.github.com/repos/iijmiolumia939/aituber/actions/runs/{run['id']}/jobs")
        for job in jobs["jobs"]:
            print(f"  [{job['conclusion'] or job['status']}] {job['name']}")
            if job["conclusion"] == "failure":
                for step in job["steps"]:
                    if step.get("conclusion") == "failure":
                        print(f"    STEP FAIL: {step['name']}")

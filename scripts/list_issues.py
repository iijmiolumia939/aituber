import urllib.request, json
TOKEN = open("scripts/create_embodied_ai_issues.py", encoding="utf-8").read().split('TOKEN  = "')[1].split('"')[0]
req = urllib.request.Request(
    "https://api.github.com/repos/iijmiolumia939/aituber/issues?state=open&per_page=30",
    headers={"Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json"},
)
issues = json.loads(urllib.request.urlopen(req).read())
for i in sorted(issues, key=lambda x: x["number"]):
    labels = "|".join(l["name"] for l in i["labels"])
    print("#" + str(i["number"]).rjust(3) + " [" + labels + "] " + i["title"])

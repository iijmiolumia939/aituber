#!/usr/bin/env python
import sys, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRS = ROOT / ".github" / "srs"

def load(path: pathlib.Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def require_ids(items, prefix):
    ids = []
    for it in items:
        _id = it.get("id")
        if not _id or not _id.startswith(prefix):
            raise SystemExit(f"Invalid or missing id with prefix {prefix}: {it}")
        ids.append(_id)
    if len(ids) != len(set(ids)):
        raise SystemExit(f"Duplicate IDs found for {prefix}")
    return set(ids)

def main():
    req = load(SRS / "requirements.yml")
    nfr = load(SRS / "nfr.yml")
    tcs = load(SRS / "tests.yml")

    fr_ids = require_ids(req.get("fr", []), "FR-")
    nfr_ids = require_ids(nfr.get("nfr", []), "NFR-")
    _ = require_ids(tcs.get("tests", []), "TC-")

    for tc in tcs.get("tests", []):
        for m in tc.get("maps_to", []):
            if m.startswith("FR-") and m not in fr_ids:
                raise SystemExit(f"{tc['id']} maps_to unknown FR id: {m}")
            if m.startswith("NFR-") and m not in nfr_ids:
                raise SystemExit(f"{tc['id']} maps_to unknown NFR id: {m}")

    print("OK: SRS YAML validated.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
import sys, json, pathlib
from jsonschema import validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
schema_path = ROOT / ".github" / "srs" / "schemas" / "avatar_message.schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))

examples = [
    {"id":"01J","ts":"2026-02-22T21:00:00+09:00","cmd":"avatar_update","params":{"emotion":"neutral","gesture":"none","look_target":"camera","mouth_open":0.0}},
    {"id":"01J","ts":"2026-02-22T21:00:00+09:00","cmd":"avatar_viseme","params":{"utterance_id":"utt","viseme_set":"jp_basic_8","events":[{"t_ms":0,"v":"sil"}],"crossfade_ms":60,"strength":1.0}},
    {"id":"01J","ts":"2026-02-22T21:00:00+09:00","type":"capabilities","caps":{"mouth_open":True,"viseme":True,"viseme_set":["jp_basic_8"]}},
]

def main():
    for ex in examples:
        validate(instance=ex, schema=schema)
    print("OK: avatar schema examples valid.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

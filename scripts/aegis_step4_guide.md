# Aegis Step 4 Guide (Admin Surface)

Use this after Step 1-3 are done.

## Import seed docs

Read payloads from:

- scripts/aegis_seed_import_payloads.json

For each item, call `aegis_import_doc` in admin surface.

Required fields in each call:

- file_path
- doc_id
- title
- kind
- edge_hints
- tags

## Verify deterministic compile

After imports, run in agent surface:

1) C# target example

- aegis_compile_context
- target_files: ["AITuber/Assets/Scripts/AvatarController.cs"]
- command: "review"

2) Python target example

- aegis_compile_context
- target_files: ["AITuber/orchestrator/main.py"]
- command: "review"

## Record misses

If required guideline was missing in returned context, report:

- aegis_observe
- event_type: compile_miss
- related_compile_id: <from compile_context>
- related_snapshot_id: <from compile_context>
- payload.target_files: [<edited file path>]
- payload.review_comment: <what was missing>
- payload.target_doc_id or payload.missing_doc if identifiable

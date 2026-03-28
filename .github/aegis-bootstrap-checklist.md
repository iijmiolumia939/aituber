# Aegis Bootstrap Checklist (Steps 1-4)

Use this checklist in the Aegis admin surface.

## Step 1: init detect

Call:

- aegis_init_detect

Recommended payload:

- project_root: <absolute path to your repository root>
- skip_template: true

Keep the returned preview_hash for Step 2.

## Step 2: init confirm

Call:

- aegis_init_confirm

Payload:

- preview_hash: <from Step 1>

Expected result:

- .aegis/aegis.db is created

## Step 3: deploy adapters

Run in terminal:

- ./scripts/setup_aegis.ps1

Expected result:

- Adapter deployment succeeds without DB-not-found error.

## Step 4: import initial docs with edge hints

Call aegis_import_doc repeatedly for core documents.

Recommended first import set:

- AGENTS.md
- .github/copilot-instructions.md
- AITuber/.github/copilot-review-workflow.md
- ARCHITECTURE.md
- QUALITY_SCORE.md

Suggested edge_hints examples:

1) For AGENTS.md
- source_type: path
- source_value: AGENTS.md
- edge_type: path_requires

2) For copilot instructions
- source_type: path
- source_value: .github/copilot-instructions.md
- edge_type: path_requires

3) For C# runtime rules
- source_type: path
- source_value: AITuber/Assets/Scripts/
- edge_type: path_requires

4) For Python orchestrator rules
- source_type: path
- source_value: AITuber/orchestrator/
- edge_type: path_requires

After imports:

- Run aegis_compile_context for one C# file and one Python file to confirm deterministic retrieval.
- If something is missing, record aegis_observe with event_type compile_miss.

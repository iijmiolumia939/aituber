# Aegis Process Enforcement

You MUST consult Aegis for every coding-related interaction — implementation tasks AND questions about architecture, patterns, or conventions. No exceptions.

## When Writing Code

1. **Create a Plan** — Before touching any file, articulate what you intend to do.
2. **Consult Aegis** — Call `aegis_compile_context` with:
   - `target_files`: the files you plan to edit
   - `plan`: your natural-language plan (optional but recommended)
   - `command`: the type of operation (scaffold, refactor, review, etc.)
3. **Read and follow** the returned architecture guidelines.
4. **Self-Review** — After writing code, check your implementation against the returned guidelines.
5. **Report Compile Misses** — If Aegis failed to provide a needed guideline:
   ```
   aegis_observe({
     event_type: "compile_miss",
     related_compile_id: "<from step 2>",
     related_snapshot_id: "<from step 2>",
     payload: {
       target_files: ["<files>"],
       review_comment: "<what was missing or insufficient>",
       target_doc_id: "<optional: base.documents[*].doc_id whose content was insufficient>",
       missing_doc: "<optional: doc_id that should have been returned but was not>"
     }
   })
   ```

## When Answering Questions

1. **Identify representative files** — Find 1–3 real file paths relevant to the question.
2. **Consult Aegis** — Call `aegis_compile_context` with `command: "review"`.
3. **Answer using Aegis context** — Base your answer on the returned guidelines.

## Rules

- NEVER skip the Aegis consultation step.
- NEVER ignore guidelines returned by Aegis.
- The compile_id and snapshot_id from the consultation are required for observation reporting.

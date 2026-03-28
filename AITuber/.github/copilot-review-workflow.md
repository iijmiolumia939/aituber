# Copilot AI Review Workflow

This repository uses a harness-style review loop rather than a single review pass.

Start from `Task: Harness: Review Packet`. It writes `copilot-temp/review-packet.md` and tells you which reviewers and validations are relevant to the current diff.

Before implementation and architecture Q&A, call `aegis_compile_context` with target files and follow returned guidance.

When you run `/run-harness-review-loop` or `Harness Review Orchestrator`, persist the latest result to `copilot-temp/review-loop-latest.md` and append one JSON line to `copilot-temp/review-loop-history.jsonl`.

Domain reviewers live in `.github/copilot-review-prompts/`:

| ファイル | 担当領域 |
|---|---|
| [requirements-reviewer.md](copilot-review-prompts/requirements-reviewer.md) | FR/NFR/TC 要件適合 |
| [architecture-reviewer.md](copilot-review-prompts/architecture-reviewer.md) | 依存方向・責務・IK順序 |
| [reliability-reviewer.md](copilot-review-prompts/reliability-reviewer.md) | CC/NavMesh 競合・二重起動リスク |
| [security-reviewer.md](copilot-review-prompts/security-reviewer.md) | セキュリティ（必要時） |
| [performance-reviewer.md](copilot-review-prompts/performance-reviewer.md) | パフォーマンス（必要時） |
| [test-reviewer.md](copilot-review-prompts/test-reviewer.md) | テストカバレッジ |
| [lead-reviewer.md](copilot-review-prompts/lead-reviewer.md) | 最終統合判定 |

Loop-control prompts live in `.github/prompts/`:

| ファイル | 役割 |
|---|---|
| [run-harness-review-loop.prompt.md](prompts/run-harness-review-loop.prompt.md) | review packet を起点に reviewer, triage, validate を 1 回で回す |
| [triage-review-findings.prompt.md](prompts/triage-review-findings.prompt.md) | 過剰指摘の除外、severity 判定、directive 固定 |
| [validate-review-fixes.prompt.md](prompts/validate-review-fixes.prompt.md) | バンドエイド修正の検出、根本原因対処の確認 |

Custom agent:

| ファイル | 役割 |
|---|---|
| [harness-review-orchestrator.agent.md](agents/harness-review-orchestrator.agent.md) | current diff 向けの review loop をまとめて扱う |

## 事前チェック（C# 編集後）

1. **Unity コンパイル確認** — `mcp_unitymcp_validate_script` で編集ファイルを検証（0 errors 必須）
2. **Unity リフレッシュ** — `mcp_unitymcp_refresh_unity(compile="request", wait_for_ready=true)`
3. **コンソール確認** — `mcp_unitymcp_read_console(types=["error","warning"])` で 0 件確認

## レビュー実施順

1. `Task: Harness: Review Packet` を実行し、`copilot-temp/review-packet.md` を確認する
2. `/run-harness-review-loop` または `Harness Review Orchestrator` を使う。手動で回す場合のみ Domain reviewers を個別実行する
3. `/triage-review-findings` で findings を整理する
4. Must Fix のみ修正する
5. `/validate-review-fixes` で根本原因に対処できているか確認する
6. `Task: Harness: Quality Gate (changed files)` を通す
7. Must Fix が 0 件になるまで 2〜6 を最大 6 回繰り返す

## Auto Trigger

- `pre-commit` は `scripts/copilot_pre_commit.ps1` を自動実行し、review packet 再生成と changed-files quality gate を行う
- Unity C# 変更がある場合、`pre-commit` は `copilot-temp/unity-validation.json` が最新であることも要求する
- `pre-commit` で自動化できるのは deterministic な shell steps のみ
- LLM を使う reviewer / triage / validate は git hook で安定実行できないため、`/run-harness-review-loop` か custom agent で回す
- Unity C# compile / console validation は Unity Editor 状態に依存するため、hook では未自動化。C# 変更時は Unity MCP 手順を別途必須とする
- Unity MCP の確認後は `Task: Harness: Mark Unity Validation Done` を実行して marker を更新する
- 別リポジトリへハーネスを導入した直後に既存の Unity C# 変更がある場合、最初の `pre-commit` はこの marker 要件で止まる

## Aegis Process

1. `aegis_compile_context` を target files 付きで呼ぶ
2. 返ってきた guideline/constraint/template に従って実装する
3. 不足していたルールがレビューで見つかった場合は `aegis_observe` (`compile_miss`) で報告する
4. Admin surface で proposal を triage して承認/却下する

## Domain Reviewers

1. Requirements Reviewer — SRS FR/NFR/TC ID 照合
2. Architecture Reviewer — 依存方向・IK スタック責務
3. Reliability Reviewer — CC/NavMesh 競合・BeginSnap 二重呼び出しリスク
4. Security Reviewer（変更に認証/外部入力が含まれる場合）
5. Performance Reviewer（ホットパス変更がある場合）
6. Test Reviewer — カバレッジギャップ
7. Lead Reviewer — 最終統合判定・LGTM or BLOCK

## Triage Rules

- `LOW` は原則捨てる。直すのは `CRITICAL` と `IMPORTANT` のみ
- 変更していない既存コードへの指摘は原則捨てる
- ただし今回の diff が既存不具合を露出させる場合は `CRITICAL` として残す
- 前回イテレーションと逆方向の修正提案は oscillation とみなし、より良い方を directive として固定する
- fix ステップは directive に従う。レビューごとに方針を揺らさない

## Stop Condition

- `Must Fix This Iteration` が 0 件
- `validate-review-fixes` が root-cause fixed / no blocker を返す
- quality gate が成功する

## Philosophy

Each reviewer focuses on ONE domain to ensure deeper analysis.

Avoid mixing concerns.

The harness exists to constrain, inform, verify, and correct. Do not skip triage or validation just because the first review output looks clean.

## Severity Definitions

Critical:
Breaks production / security / data integrity.

High:
Major design or reliability issue.

Medium:
Important improvement.

Low:
Minor suggestion.

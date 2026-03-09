# Copilot AI Review Workflow

This repository uses structured AI review prompts located in
`.github/copilot-review-prompts/`:

| ファイル | 担当領域 |
|---|---|
| [requirements-reviewer.md](copilot-review-prompts/requirements-reviewer.md) | FR/NFR/TC 要件適合 |
| [architecture-reviewer.md](copilot-review-prompts/architecture-reviewer.md) | 依存方向・責務・IK順序 |
| [reliability-reviewer.md](copilot-review-prompts/reliability-reviewer.md) | CC/NavMesh 競合・二重起動リスク |
| [security-reviewer.md](copilot-review-prompts/security-reviewer.md) | セキュリティ（必要時） |
| [performance-reviewer.md](copilot-review-prompts/performance-reviewer.md) | パフォーマンス（必要時） |
| [test-reviewer.md](copilot-review-prompts/test-reviewer.md) | テストカバレッジ |
| [lead-reviewer.md](copilot-review-prompts/lead-reviewer.md) | 最終統合判定 |

## 事前チェック（C# 編集後）

1. **Unity コンパイル確認** — `mcp_unitymcp_validate_script` で編集ファイルを検証（0 errors 必須）
2. **Unity リフレッシュ** — `mcp_unitymcp_refresh_unity(compile="request", wait_for_ready=true)`
3. **コンソール確認** — `mcp_unitymcp_read_console(types=["error","warning"])` で 0 件確認

## レビュー実施順

1. Requirements Reviewer — SRS FR/NFR/TC ID 照合
2. Architecture Reviewer — 依存方向・IK スタック責務
3. Reliability Reviewer — CC/NavMesh 競合・BeginSnap 二重呼び出しリスク
4. Security Reviewer（変更に認証/外部入力が含まれる場合）
5. Performance Reviewer（ホットパス変更がある場合）
6. Test Reviewer — カバレッジギャップ
7. Lead Reviewer — 最終統合判定・LGTM or BLOCK

## Philosophy

Each reviewer focuses on ONE domain to ensure deeper analysis.

Avoid mixing concerns.

## Severity Definitions

Critical:
Breaks production / security / data integrity.

High:
Major design or reliability issue.

Medium:
Important improvement.

Low:
Minor suggestion.

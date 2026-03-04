# PLANS.md — AITuber 実装計画トラッカー

> **最終更新**: 2026-03-04 (M15 完了)  
> これは計画の索引です。詳細はリンク先の exec-plan を参照。  
> 完了した計画は `exec-plans/completed/` に移動し、ここでは状態を「✅完了」に更新する。

---

## 進行中

*現在進行中のタスクはありません。*

<!-- M10 完了 2026-03-04 → [exec-plans/completed/m10-tts-tests.md](AITuber/docs/exec-plans/completed/m10-tts-tests.md) -->

---

## バックログ

| 計画 | 優先度 | 依存 | 概要 |
|---|---|---|---|

*バックログは現在空です。*

---

## 完了済み

| 計画 | 完了日 | 成果 | 詳細 |
|---|---|---|---|
| M1: ActionDispatcher + GapLogger | 2026-03-03 | 61/61テスト グリーン | [exec-plans/completed/m1-gap-logger.md](AITuber/docs/exec-plans/completed/m1-gap-logger.md) |
| M2: ReflectionRunner (LLM-Modulo) | 2026-03-03 | 41/41テスト グリーン, ruff クリーン | [exec-plans/completed/m2-reflection-runner.md](AITuber/docs/exec-plans/completed/m2-reflection-runner.md) |
| M3: GapDashboard (Gap 集計 CLI) | 2026-03-03 | 26/26テスト グリーン, ruff クリーン | [exec-plans/completed/m3-gap-dashboard.md](AITuber/docs/exec-plans/completed/m3-gap-dashboard.md) |
| M4: 上位Gap 手動実装（初回成長） | 2026-03-04 | 24/24テスト グリーン, behavior_policy +7エントリ | [exec-plans/completed/m4-top-gap-impl.md](AITuber/docs/exec-plans/completed/m4-top-gap-impl.md) |
| M5: ReflectionRunner end-to-end 配線 | 2026-03-04 | 11/11テスト グリーン, TD-010 解消 | [exec-plans/completed/m5-reflection-cli.md](AITuber/docs/exec-plans/completed/m5-reflection-cli.md) |
| M6: 人間承認フロー (ApproveCLI / Phase 2) | 2026-03-04 | 14/14テスト グリーン, Phase 2 Growth Loop 全配線 | [exec-plans/completed/m6-approve-cli.md](AITuber/docs/exec-plans/completed/m6-approve-cli.md) |
| M7: GrowthLoop フル統合オーケストレーター | 2026-03-04 | 13/13テスト グリーン, ruff クリーン, 353/355 passed | [exec-plans/completed/m7-growth-loop.md](AITuber/docs/exec-plans/completed/m7-growth-loop.md) |
| M8: 自律コード生成スコープ拡張 (Phase 2b) | 2026-03-04 | 50/50テスト グリーン, FR-SCOPE-01/02, 403 passed | [exec-plans/completed/m8-scope-expansion.md](AITuber/docs/exec-plans/completed/m8-scope-expansion.md) |
| M9: WebSocket スキーマバリデーション | 2026-03-04 | 41/41テスト グリーン, FR-WS-SCHEMA-01/02, 444 passed | [exec-plans/completed/m9-ws-schema.md](AITuber/docs/exec-plans/completed/m9-ws-schema.md) |
| M10: TTS/AudioPlayer テスト強化 | 2026-03-04 | 23/23テスト グリーン, FR-LIPSYNC-01/02, 467 passed | [exec-plans/completed/m10-tts-tests.md](AITuber/docs/exec-plans/completed/m10-tts-tests.md) |
| M11: Bandit ε自動調整 | 2026-03-04 | 14/14テスト グリーン, FR-BANDIT-EPS-01, 481 passed | exec-plans/completed/m11-bandit-epsilon.md |
| M12: Room/Environment テスト強化 | 2026-03-04 | 18/18テスト グリーン (Unity EditMode), FR-ROOM-01/02, TC-ROOM-01〜18 | — |
| M13: CI Unity ビルド自動化 | 2026-03-04 | .github/workflows/ci.yml + unity-ci.yml 新設 (EditMode/PlayMode) | — |
| M14: Overlay 自動テスト | 2026-03-04 | 20/20テスト グリーン (Python), TC-OVL-01〜20, overlay_server.py バグ修正 | — |
| M15: LLM バックエンド切替 | 2026-03-04 | 6/6テスト グリーン, FR-LLM-BACKEND-01, LLM_BASE_URL/LLM_MODEL 環境変数, 507 passed | — |

---

## 計画追加ルール

1. 新しい機能実装は必ずここにバックログとして追加してから着手
2. 複雑な計画（3日以上かかる場合）は `exec-plans/active/` に詳細 exec-plan を作成
3. 軽微な変更（1日以内）は PR 説明で代替可
4. 完了後は exec-plan に完了ログを追記し `completed/` に移動

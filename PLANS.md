# PLANS.md — AITuber 実装計画トラッカー

> **最終更新**: 2026-03-03 (M3 GapDashboard 完了)  
> これは計画の索引です。詳細はリンク先の exec-plan を参照。  
> 完了した計画は `exec-plans/completed/` に移動し、ここでは状態を「✅完了」に更新する。

---

## 進行中

| 計画 | 優先度 | ステータス | exec-plan |
|---|---|---|---|
| M3: GapDashboard (Gap 集計 CLI) | 🔴 高 | ✅ 完了 (2026-03-03) | [exec-plans/completed/m3-gap-dashboard.md](AITuber/docs/exec-plans/completed/m3-gap-dashboard.md) |

---

## バックログ

| 計画 | 優先度 | 依存 | 概要 |
|---|---|---|---|
| M4: 上位Gap 手動実装（初回成長） | 🔴 高 | M3完了 | GapDashboard の集計結果を元に上位 Gap のモーションを手動実装 |
| M5→: 自律コード生成 (BehaviorPolicy自動拡張) | 🟡 中 | M4完了 | LLM提案→YAML自動マージ + 人間承認フロー（自律成長 Phase 2） |
| TTS/AudioPlayer テスト強化 | 🟡 中 | なし | VOICEVOX モック、音素テーブル検証 |
| WebSocket スキーマバリデーション | 🟡 中 | なし | 受信時 JSON Schema チェック実装 |
| Room/Environment テスト強化 | 🟠 低 | なし | ScriptableObject シリアライズ、Prefab 読み込み検証 |
| Bandit ε自動調整 | 🟠 低 | なし | 配信視聴者数に応じた探索率動的変更 |
| CI Unity ビルド自動化 | 🟠 低 | なし | GitHub Actions でヘッドレス Unity ビルド |
| Overlay 自動テスト | 🟠 低 | なし | Chrome DevTools Protocol or Playwright |

---

## 完了済み

| 計画 | 完了日 | 成果 | 詳細 |
|---|---|---|---|
| M1: ActionDispatcher + GapLogger | 2026-03-03 | 61/61テスト グリーン | [exec-plans/completed/m1-gap-logger.md](AITuber/docs/exec-plans/completed/m1-gap-logger.md) |
| M2: ReflectionRunner (LLM-Modulo) | 2026-03-03 | 41/41テスト グリーン, ruff クリーン | [exec-plans/completed/m2-reflection-runner.md](AITuber/docs/exec-plans/completed/m2-reflection-runner.md) |

---

## 計画追加ルール

1. 新しい機能実装は必ずここにバックログとして追加してから着手
2. 複雑な計画（3日以上かかる場合）は `exec-plans/active/` に詳細 exec-plan を作成
3. 軽微な変更（1日以内）は PR 説明で代替可
4. 完了後は exec-plan に完了ログを追記し `completed/` に移動

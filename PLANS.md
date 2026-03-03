# PLANS.md — AITuber 実装計画トラッカー

> **最終更新**: 2026-03-03 (M2完了)  
> これは計画の索引です。詳細はリンク先の exec-plan を参照。  
> 完了した計画は `exec-plans/completed/` に移動し、ここでは状態を「✅完了」に更新する。

---

## 進行中

*現在アクティブな計画なし。M3 はバックログで優先度評価待ち。*

---

## バックログ

| 計画 | 優先度 | 依存 | 概要 |
|---|---|---|---|
| M3: 自律コード生成 (BehaviorPolicy自動拡張) | 🟡 中 | M2完了 | LLM提案→YAML自動マージ + 人間承認フロー |
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

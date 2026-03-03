# M1: ActionDispatcher + GapLogger exec-plan (完了)

> **作成**: 2026-03  
> **完了**: 2026-03-03  
> **目標**: Intent→Action 変換ゲートウェイと Capability Gap ログ収集の実装  
> **関連**: autonomous-growth.md M1, m1-design.md, PLANS.md

---

## 達成した成果

- `ActionDispatcher`, `GapLogger`, `BehaviorPolicyLoader`, `BehaviorEntry`, `GapEntry` 全実装
- `AvatarMessage.cs` に `AvatarIntentParams` 追加
- `behavior_policy.yml` 初版作成
- Unity EditMode 55件 + PlayMode 6件 = **61/61 テスト グリーン**
- シングルトン EditMode 分離問題を解決  
  → `ClearInstanceForTest()` + `SetGapLoggerForTest()` / `SetPolicyLoaderForTest()` パターン確立

## 主要設計決定

- `ActionDispatcher` は `GetComponent<>()` でコーローカルコンポーネントを優先参照し、グローバルシングルトンへのフォールバックを維持。EditMode テスト分離に対応。
- `DispatchResult` を `ActionDispatcher` 外部のトップレベル `enum` に昇格（テストからの参照を容易にするため）
- `DontDestroyOnLoad` は `Application.isPlaying` 条件付き（EditMode 互換）

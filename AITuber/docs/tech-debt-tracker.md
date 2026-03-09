# 技術的負債トラッカー

> **方針 (2026-03-06〜)**: 技術的負債・バグ・改善は **GitHub Issues を Single Source of Truth** とする。
> このファイルは GitHub Issues へのインデックス。詳細・議論・進捗は Issue 側に記載すること。  
> 新しい負債は `gh issue create` で Issue を作成し、下表に ID とリンクを追記する。  
> 解消時は Issue を close し、下表を「解消済み」に移動する。

---

## Open（GitHub Issues）

| TD | Issue | ドメイン | 概要 |
|---|---|---|---|
| TD-001 | [#39](https://github.com/iijmiolumia939/aituber/issues/39) | TTS/Audio | `tts.py`/`audio_player.py` 自動テスト未整備 |
| TD-002 | [#40](https://github.com/iijmiolumia939/aituber/issues/40) | GapLogger | `GapLogger.Log()` が同期 I/O |
| TD-003 | [#41](https://github.com/iijmiolumia939/aituber/issues/41) | BehaviorPolicy | `behavior_policy.yml` スキーマバリデーションなし |
| TD-007 | （Issue未作成） | Bandit | ε値ハードコード、動的調整なし |
| TD-008 | [#42](https://github.com/iijmiolumia939/aituber/issues/42) | Memory | コメント履歴が再起動で消える |
| TD-009 | [#43](https://github.com/iijmiolumia939/aituber/issues/43) | AvatarController | ApplyFromPolicy と直接パスが混在 |
| TD-012 | [#36](https://github.com/iijmiolumia939/aituber/issues/36) | BehaviorSeq | `StepWalkTo` が NavMesh 未使用、壁すり抜け |
| TD-013 | [#38](https://github.com/iijmiolumia939/aituber/issues/38) | BehaviorSeq | 歩行アニメーションと移動速度の不一致 |

## 解消済み

| ID | 内容 | 解消方法 | 解消日 |
|---|---|---|---|
| TD-S01 | EditMode でシングルトン汚染 (`Instance` が stale) | `ClearInstanceForTest()` + `SetGapLoggerForTest()` / `SetPolicyLoaderForTest()` + Awake で `GetComponent` キャッシュ | 2026-03-03 |
| TD-S02 | `GapLogger.SetLogPathForTest()` で `_streamId` が空のままになるケース | `SetLogPathForTest()` 内で `_streamId` の初期化を保証 | 2026-03-03 |
| TD-011 | `priority_score` 算出式未実装 (すべて 0.0) | `GapDashboard.compute_priority_scores()` で `(freq/total) × (1/cost_weight)` を実装 (M3) | 2026-03-03 |
| TD-010 | `ReflectionRunner.generate_proposals()` が `backend=None` で空リスト返却。実配信で Reflection が動作しない | `reflection_cli.py` で `OpenAIBackend` を注入する Growth Loop CLI を実装 (M5)。11/11 TC グリーン | 2026-03-04 |

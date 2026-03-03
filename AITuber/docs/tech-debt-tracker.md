# 技術的負債トラッカー

> **ルール**: 技術的負債を認識したら即座にここに追記する。  
> QUALITY_SCORE.md の改善優先度と対応させること。  
> 定期的（週1）に棚卸しし、解消済みのものは「✅解消」に更新する。

---

## 高優先度 (対応要)

| ID | ドメイン | 内容 | 影響 | 追加日 |
|---|---|---|---|---|
| TD-001 | TTS/Audio | `tts.py` / `audio_player.py` の自動テストなし。VOICEVOX 起動必須で CI が通らない | 音素マッピングバグを検出できない | 2026-03 |
| TD-002 | GapLogger | `GapLogger.Log()` がメインスレッド同期 I/O。高頻度配信でフレームドロップの可能性 | 高頻度配信時のパフォーマンス劣化 | 2026-03 |
| TD-003 | BehaviorPolicy | `behavior_policy.yml` にスキーマバリデーションなし。誤ったフィールドが silently skip される | 設定ミスが実行時まで発覚しない | 2026-03 |

## 中優先度 (次スプリント)

| ID | ドメイン | 内容 | 影響 | 追加日 |
|---|---|---|---|---|
| TD-004 | WebSocket | 受信 JSON のスキーマバリデーション未実装。不正コマンドがそのまま処理される | 外部からの不正コマンドへの脆弱性 | 2026-03 |
| TD-005 | Room | `RoomManager` のテストなし。Prefab 読み込み・切り替えが手動確認のみ | リグレッション検知不可 | 2026-03 |
| TD-006 | CI | Unity ヘッドレスビルドが CI に含まれない。コンパイルエラーを PR 前に検知できない | C# コンパイルエラーが master に入りうる | 2026-03 |

## 低優先度 (将来対応)

| ID | ドメイン | 内容 | 影響 | 追加日 |
|---|---|---|---|---|
| TD-007 | Bandit | ε値がハードコード。視聴者数・配信時間に応じた動的調整なし | 探索/活用のバランスが最適でない | 2026-03 |
| TD-008 | Memory | `memory.py` のコメント履歴が Python dict のみ。再起動で消える | 配信再開時に文脈が失われる | 2026-03 |
| TD-009 | AvatarController | `ApplyFromPolicy()` と直接コマンド受信パスが混在。統一できていない | 将来の拡張時に複雑化 | 2026-03 |
| TD-010 | ReflectionRunner | `ReflectionRunner.generate_proposals()` は `backend=None` の場合に空リストを返す。実際の LLM 呼び出しには外部から `OpenAIBackend` を注入するワイヤリングコードが未作成 | 実配信での自動 Reflection が動作しない | 2026-03-03 |
## 解消済み

| ID | 内容 | 解消方法 | 解消日 |
|---|---|---|---|
| TD-S01 | EditMode でシングルトン汚染 (`Instance` が stale) | `ClearInstanceForTest()` + `SetGapLoggerForTest()` / `SetPolicyLoaderForTest()` + Awake で `GetComponent` キャッシュ | 2026-03-03 |
| TD-S02 | `GapLogger.SetLogPathForTest()` で `_streamId` が空のままになるケース | `SetLogPathForTest()` 内で `_streamId` の初期化を保証 | 2026-03-03 |
| TD-011 | `priority_score` 算出式未実装 (すべて 0.0) | `GapDashboard.compute_priority_scores()` で `(freq/total) × (1/cost_weight)` を実装 (M3) | 2026-03-03 |

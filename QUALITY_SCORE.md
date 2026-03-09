# QUALITY_SCORE.md — AITuber 品質スコアカード

> **最終更新**: 2026-03-05 (M20完了)  
> **更新ルール**: PR マージ後、影響するドメインのスコアを更新する。  
> 改善が必要な領域は `tech-debt-tracker.md` にも反映すること。

グレード定義: A=安定・テスト完備 / B=動作するが改善余地あり / C=脆弱・要注意 / D=未実装・使用不可

---

## フィーチャードメイン別

| ドメイン | グレード | テストカバレッジ | 主な懸念点 |
|---|---|---|---|
| ChatPoller (FR-A3) | B | 中（モック中心） | 実YouTube APIとの e2e テストなし |
| Safety / Content Filter (FR-SAFE) | B | 高 | GRAY判定の境界ケース不十分 |
| Bandit / RL (FR-RL) | A | 高 (14/14 TC) | M11: ε自動調整(adapt_epsilon)実装済み。永続化が JSON ファイル |
| LLM Client (FR-LLM) | A | 高 | M15: LLM_BASE_URL/LLM_MODELでOpenAI互換任意バックエンド切替対応。TC-LLM-BACKEND-01〜06 |
| TTS / LipSync (FR-LIPSYNC) | B | 中 | M10: extract_visemes + VoicevoxBackend モック。23/23 TC |
| AudioPlayer | B | 中 | M10: sounddevice モック化。テスト完備 |
| AvatarController (全般) | B | 中 | Unity PlayMode テスト不足 |
| Room/Environment (FR-ROOM) | B | 高 (18/18 TC) | M12: ScriptableObject+RoomManager EditMode テスト完備 |
| Growth/GapLogger (M1) | A | 高 (12/12 TC) | ファイルI/O 同期のみ。高頻度配信で懸念 |
| Growth/ActionDispatcher (M1) | A | 高 (15/15 TC) | AvatarController stub依存。実機テストなし |
| Growth/BehaviorPolicyLoader (M1) | A | 高 (15/15 TC) | YAML スキーマバリデーションなし |
| Growth/ReflectionRunner (M2) | A | 高 (41/41 TC) | LLM 本番呼び出しなし (モックのみ)。CLI は M5 で整備済み |
| Growth/ReflectionCLI (M5) | A | 高 (11/11 TC) | end-to-end Growth Loop wiring。TD-010 解消 |
| Growth/ApproveCLI (M6) | A | 高 (14/14 TC) | 人間承認フロー完成。Phase 2 Growth Loop 全配線 |
| Growth/GapDashboard (M3) | A | 高 (26/26 TC) | rich 未インストールの場合はプレーンテキストフォールバック |
| Growth/PolicyGrowth (M4) | A | 高 (24/24 TC) | behavior_policy.yml に 7 エントリ追加。実機テストは次回配信待ち |
| WebSocket プロトコル準拠 | A | 高 (41/41 TC) | M9: WsSchemaValidator 実装済み。FR-WS-SCHEMA-01/02 達成 |
| Overlay / OBS 連携 | B | 中 | M14: Python 20件 (TC-OVL-01〜20)。HTML overlay 手動確認のみ |
| Growth/BanditEpsilon (M11) | A | 高 (14/14 TC) | FR-BANDIT-EPS-01。ε自動調整 + auto_adapt 実装済み |
| Growth/WsSchemaValidator (M9) | A | 高 (41/41 TC) | FR-WS-SCHEMA-01/02。受信時 JSON Schema バリデーション |
| Growth/LiveChatId (M16) | A | 高 (9/9 TC) | FR-CHATID-AUTO-01。fetch_active_live_chat_id + Orchestrator._resolve_live_chat_id |
| Growth/YuiaIntents (M17) | A | 高 (21/21 TC) | FR-YUIA-INT-01〜06。behavior_policy +6 YUI.A intents |
| Behavior/BehaviorDefinitionLoader (M20) | B | 中 (テスト未実装) | FR-BEHAVIOR-SEQ-01。behaviors.json ロード+ルックアップシングルトン |
| Behavior/BehaviorSequenceRunner (M20) | B | 中 (テスト未実装) | FR-BEHAVIOR-SEQ-01。walk_to/gesture/wait コルーチン |

---

## アーキテクチャ層別

| 層 | グレード | コメント |
|---|---|---|
| Python Orchestrator 全体 | B | 依存関係は概ね整理済み。循環依存なし |
| C# Runtime アセンブリ設計 | A | AITuber.Runtime 単一。依存境界明確 |
| WebSocket プロトコル定義 | A | M9: WsSchemaValidator実装済み。C#バリデーションは Python 側で完了 |
| テスト戦略 (Python) | B | pytest カバレッジ中程度 |
| テスト戦略 (C# Unity) | A | 61/61 テスト グリーン (EditMode 55 + PlayMode 6) |
| CI/CD パイプライン | B | M13: ci.yml(Python ruff+black+pytest) + unity-ci.yml(game-ci EditMode/PlayMode) |
| ドキュメント | B | 設計書あり。Harness Engineering 方式に刷新中 |
| セキュリティ | B | secrets 分離済み。GitHub Secret Scanning 有効 |

---

## テスト集計（2026-03-05 時点）

| スイート | 合計 | 合格 | 失敗 |
|---|---|---|---|
| Unity EditMode | 55 | 55 | 0 |
| Unity PlayMode | 6 | 6 | 0 |
| Python pytest (new M2) | 41 | 41 | 0 |
| Python pytest (new M3) | 26 | 26 | 0 |
| Python pytest (new M4) | 24 | 24 | 0 |
| Python pytest (new M5) | 11 | 11 | 0 |
| Python pytest (new M6) | 14 | 14 | 0 |
| Python pytest (new M7) | 13 | 13 | 0 |
| Python pytest (new M8) | 50 | 50 | 0 |
| Python pytest (new M9) | 41 | 41 | 0 |
| Python pytest (new M10) | 23 | 23 | 0 |
| Python pytest (new M11) | 14 | 14 | 0 |
| Python pytest (new M14) | 20 | 20 | 0 |
| Python pytest (new M15) | 6 | 6 | 0 |
| Python pytest (new M16) | 9 | 9 | 0 |
| Python pytest (new M17) | 21 | 21 | 0 |
| Python pytest (全スイート) | 507 | 507 | 2 (pre-existing: emotion_gesture_selector) |

---

## 改善優先度

1. **BehaviorSequenceRunner テスト** — EditMode テストがゼロ (B→Aのため) (TD候補)
2. **BehaviorPolicy YAML スキーマ** — 不正エントリの早期検出 (A維持) (TD-003)
3. **AvatarController PlayMode** — Unity PlayMode テスト拡充
4. **ChatPoller e2e** — 実YouTube API との統合テスト
5. ~~**TTS/AudioPlayer テスト** — M10: extract_visemes + mock。(C→B)完了~~
5. ~~**Room/Environment テスト** — M12: ScriptableObject EditMode。(C→B)完了~~
6. ~~**WebSocket スキーマバリデーション** — M9: WsSchemaValidator。(B→A)完了~~
7. ~~**Bandit ε自動調整** — M11: adapt_epsilon。(B→A)完了~~
8. ~~**CI/CD Unity ビルド** — M13: unity-ci.yml。(C→B)完了~~
9. ~~**Overlay 自動テスト** — M14: TC-OVL-01〜20。完了~~
10. ~~**M2-M8 Growth Loop 系** — (D→A)全完了~~

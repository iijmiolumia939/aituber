# マイルストーン履歴

> M1〜M29 は全て完了済み (2026-03-14)。

| マイルストーン | 状態 | 詳細 |
|---|---|---|
| M1: Capability Gap Log収集 | ✅ 完了 (2026-03-03) | 61/61テスト グリーン |
| M2: ReflectionRunner (LLM) | ✅ 完了 (2026-03-03) | 41/41テスト グリーン |
| M3: GapDashboard (Gap 集計 CLI) | ✅ 完了 (2026-03-03) | 26/26テスト グリーン |
| M4: 上位Gap 手動実装（初回成長） | ✅ 完了 (2026-03-04) | 24/24テスト グリーン, behavior_policy +7 |
| M5: ReflectionRunner end-to-end 配線 | ✅ 完了 (2026-03-04) | 11/11テスト グリーン, TD-010 解消 |
| M6: 人間承認フロー (ApproveCLI / Phase 2 Growth Loop) | ✅ 完了 (2026-03-04) | 14/14テスト グリーン, Phase 2 全配線 |
| M7: GrowthLoop フル統合オーケストレーター | ✅ 完了 (2026-03-04) | 13/13テスト グリーン, FR-LOOP-01/02, growth_loop.py |
| M8: 自律コード生成スコープ拡張 (Phase 2b) | ✅ 完了 (2026-03-04) | 50/50テスト グリーン, FR-SCOPE-01/02, ScopeConfig + LLMModuloValidator |
| M9: WebSocket スキーマバリデーション | ✅ 完了 (2026-03-04) | 41/41テスト グリーン, FR-WS-SCHEMA-01/02, WsSchemaValidator |
| M10: TTS/AudioPlayer テスト強化 | ✅ 完了 (2026-03-04) | 23/23テスト グリーン, FR-LIPSYNC-01/02, extract_visemes + VoicevoxBackend mock |
| M11: Bandit ε自動調整 | ✅ 完了 (2026-03-04) | 14/14テスト グリーン, FR-BANDIT-EPS-01, adapt_epsilon + auto_adapt |
| M12: Room/Environment テスト強化 | ✅ 完了 (2026-03-04) | 18/18テスト グリーン (Unity EditMode), TC-ROOM-01〜18 |
| M13: CI Unity ビルド自動化 | ✅ 完了 (2026-03-04) | .github/workflows/ci.yml + unity-ci.yml (game-ci/unity-test-runner@v4) |
| M14: Overlay 自動テスト | ✅ 完了 (2026-03-04) | 20/20テスト グリーン, TC-OVL-01〜20, overlay_server.py バグ修正 |
| M15: LLM バックエンド切替 | ✅ 完了 (2026-03-04) | 6/6テスト グリーン, FR-LLM-BACKEND-01, LLM_BASE_URL/LLM_MODEL 環境変数 |
| M16: LIVE_CHAT_ID 自動取得 | ✅ 完了 (2026-03-04) | 9/9テスト グリーン, FR-CHATID-AUTO-01, fetch_active_live_chat_id + Orchestrator._resolve_live_chat_id |
| M17: YUI.A 世界観ブラッシュアップ | ✅ 完了 (2026-03-04) | 21/21テスト グリーン, behavior_policy +6 YUI.A intents, CHARACTER_NAME=yuia デフォルト設定 |
| M18: 配信前 Inspector/設定確認 | ✅ 完了 (2026-03-04) | BlendShape全設定(26項目), TTS=47確認, VRM+Animator+Room 全OK, -c yuia 動作確認 |
| M19: 日常生活 Sims-like 行動シーケンス | ✅ 完了 (2026-03-05) | BehaviorSequenceRunner + behaviors.json, FR-LIFE-01, FR-BEHAVIOR-SEQ-01 |
| M20: 行動シーケンス完全統合 | ✅ 完了 (2026-03-05) | behavior_start cmd, BehaviorDefinitionLoader, ActionDispatcher 配線, RoomManager.TryGetZone |
| M21: LipSync 統一化 | ✅ 完了 (2026-03-09) | LipSyncMode enum (A2FNeural/TtsViseme/Hybrid), 二重書込み競合解消, Issue #56 close |
| M22: Procedural Body Gesture (A2GPlugin RMS/IIR DLL) | ✅ 完了 (2026-03-09) | A2GPlugin.dll, SetEmotionGestureScale(), FR-GESTURE-PROC-01, Issue #57 close |
| M23: Unity Sentis A2E on-device推論 | ✅ 完了 (2026-03-09) | Audio2EmotionInferer.cs, UNITY_AI_INFERENCE_ENABLED, Issue #58 close |
| M24: AivisSpeech TTS 対応 | ✅ 完了 (2026-03-09) | 7/7テスト グリーン, FR-TTS-01, TTS_BACKEND=aivisspeech, Issue #59 close |
| M25: 優先度付き Intent キュー | ✅ 完了 (2026-03-10) | 12/12テスト グリーン, FR-INTENT-PRIORITY-01, IntentItem + _intent_dispatcher, Issue #45 close |
| M26: Episodic Recall Engine | ✅ 完了 (2026-03-14) | metadata-aware recall, behavior completion ingestion, context-aware ranking |
| M27: Semantic Memory Layer | ✅ 完了 (2026-03-14) | viewer familiarity/repeated topics durable facts, semantic overview, `[FACTS]` prompt |
| M28: Narrative and Goal Continuity | ✅ 完了 (2026-03-14) | goal memory, viewer-aware continuity, ambient/scene/object grounded recall |
| M29: Runtime Memory Maintenance | ✅ 完了 (2026-03-14) | post-stream maintenance CLI, duplicate merge, stale archive, conservative semantic/goal backfill |

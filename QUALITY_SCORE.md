# QUALITY_SCORE.md — AITuber 品質スコアカード

> **最終更新**: 2026-03-04 (M6完了)  
> **更新ルール**: PR マージ後、影響するドメインのスコアを更新する。  
> 改善が必要な領域は `tech-debt-tracker.md` にも反映すること。

グレード定義: A=安定・テスト完備 / B=動作するが改善余地あり / C=脆弱・要注意 / D=未実装・使用不可

---

## フィーチャードメイン別

| ドメイン | グレード | テストカバレッジ | 主な懸念点 |
|---|---|---|---|
| ChatPoller (FR-A3) | B | 中（モック中心） | 実YouTube APIとの e2e テストなし |
| Safety / Content Filter (FR-SAFE) | B | 高 | GRAY判定の境界ケース不十分 |
| Bandit / RL (FR-RL) | B | 中 | ε値の自動調整なし、永続化が JSON ファイル |
| LLM Client (FR-LLM) | B | 中 | テンプレートフォールバックのテストあり。コスト上限B |
| TTS / LipSync (FR-LIPSYNC) | C | 低 | VOICEVOX 依存で自動テスト困難。音素マッピング未検証 |
| AudioPlayer | C | 低 | sounddevice 直叩き、テストなし |
| AvatarController (全般) | B | 中 | Unity PlayMode テスト不足 |
| Room/Environment (FR-ROOM) | C | 低 | ScriptableObject 構成テストなし |
| Growth/GapLogger (M1) | A | 高 (12/12 TC) | ファイルI/O 同期のみ。高頻度配信で懸念 |
| Growth/ActionDispatcher (M1) | A | 高 (15/15 TC) | AvatarController stub依存。実機テストなし |
| Growth/BehaviorPolicyLoader (M1) | A | 高 (15/15 TC) | YAML スキーマバリデーションなし |
| Growth/ReflectionRunner (M2) | A | 高 (41/41 TC) | LLM 本番呼び出しなし (モックのみ)。CLI は M5 で整備済み |
| Growth/ReflectionCLI (M5) | A | 高 (11/11 TC) | end-to-end Growth Loop wiring。TD-010 解消 |
| Growth/ApproveCLI (M6) | A | 高 (14/14 TC) | 人間承認フロー完成。Phase 2 Growth Loop 全配線 |
| Growth/GapDashboard (M3) | A | 高 (26/26 TC) | rich 未インストールの場合はプレーンテキストフォールバック |
| Growth/PolicyGrowth (M4) | A | 高 (24/24 TC) | behavior_policy.yml に 7 エントリ追加。実機テストは次回配信待ち |
| WebSocket プロトコル準拠 | B | 中 | スキーマバリデーション未実装 (FR-A7) |
| Overlay / OBS 連携 | C | 低 | 手動確認のみ |

---

## アーキテクチャ層別

| 層 | グレード | コメント |
|---|---|---|
| Python Orchestrator 全体 | B | 依存関係は概ね整理済み。循環依存なし |
| C# Runtime アセンブリ設計 | A | AITuber.Runtime 単一。依存境界明確 |
| WebSocket プロトコル定義 | B | YAMLで仕様化済み。C#バリデーション未実装 |
| テスト戦略 (Python) | B | pytest カバレッジ中程度 |
| テスト戦略 (C# Unity) | A | 61/61 テスト グリーン |
| CI/CD パイプライン | C | `.github/workflows/ci.yml` 存在するが実機Unityビルドなし |
| ドキュメント | B | 設計書あり。Harness Engineering 方式に刷新中 |
| セキュリティ | B | secrets 分離済み。GitHub Secret Scanning 有効 |

---

## テスト集計（2026-03-03 時点）

| スイート | 合計 | 合格 | 失敗 |
|---|---|---|---|
| Unity EditMode | 55 | 55 | 0 |
| Unity PlayMode | 6 | 6 | 0 |
| Python pytest (new M4) | 24 | 24 | 0 |
| Python pytest (new M3) | 26 | 26 | 0 |
| Python pytest (new M2) | 41 | 41 | 0 |
| Python pytest (new M5) | 11 | 11 | 0 |
| Python pytest (new M6) | 14 | 14 | 0 |
| Python pytest (new M7) | 13 | 13 | 0 |
| Python pytest (new M8) | 50 | 50 | 0 |
| Python pytest (全スイート) | 403 | 403 | 2 (pre-existing: emotion_gesture_selector) |

---

## 改善優先度

1. **TTS/AudioPlayer テスト** — VOICEVOX モック化が必要 (C→B)
2. **Room/Environment テスト** — ScriptableObject シリアライズ検証 (C→B)
3. **WebSocket スキーマバリデーション** — JSON Schema チェックを受信時に実施 (B→A)
4. **BehaviorPolicy YAML スキーマ** — 不正エントリの早期検出 (A維持)
5. ~~**M2 ReflectionRunner 実装** — (D→A)完了~~
6. ~~**M3 GapDashboard 実装** — (D→A)完了~~
7. ~~**M5 ReflectionCLI 配線** — TD-010解消完了~~
8. ~~**M6 ApproveCLI 人間承認フロー** — Phase 2 Growth Loop完成~~
9. ~~**M7 GrowthLoop 統合オーケストレーター** — FR-LOOP-01/02 実装完了~~
10. ~~**M8 ScopeConfig + LLMModuloValidator** — FR-SCOPE-01/02 実装完了、Phase 2b《起動~~

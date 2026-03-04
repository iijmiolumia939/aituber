# AGENTS.md — AITuber リポジトリ エントリポイント

> **このファイルはマップです。百科事典ではありません。**  
> 詳細は各ポインタ先のドキュメントを参照してください。  
> エージェントから見えないものは存在しない — Slack/口頭の決定はすべてここに反映済みです。

---

## システム概要

YouTube Live コメントを受け取り、AIアバターが自律応答・自律成長する配信基盤。

```
YouTube LiveChat
      │ poll FR-A3-01
      ▼
Orchestrator (Python)          ← Brain: orchestrator/
  Safety → Bandit → LLM → TTS
      │ WebSocket ws://0.0.0.0:31900
      ▼
Unity Avatar Client (C#)       ← Renderer: AITuber/Assets/Scripts/
  AvatarController (Emotion/Gesture/IK/Room)
      │ Capability Gap 未知Intent
      ▼
Growth System (C#/Python)      ← M1完了, M2計画中
  ActionDispatcher → GapLogger → ReflectionRunner(M2)
```

---

## どこに何があるか（ポインタ一覧）

| 知りたいこと | 参照先 |
|---|---|
| アーキテクチャ全体像・ドメイン境界・依存ルール | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 機能要件・非機能要件（FR/NFR/TC） | [AITuber/.github/srs/](AITuber/.github/srs/) |
| 品質グレードと既知ギャップ | [QUALITY_SCORE.md](QUALITY_SCORE.md) |
| 現在進行中の実装計画 | [PLANS.md](PLANS.md) |
| 詳細実行計画（進捗ログ付き） | [AITuber/docs/exec-plans/](AITuber/docs/exec-plans/) |
| 技術的負債リスト | [AITuber/docs/tech-debt-tracker.md](AITuber/docs/tech-debt-tracker.md) |
| 設計ドキュメント一覧 | [AITuber/docs/design-docs/index.md](AITuber/docs/design-docs/index.md) |
| C# コーディングルール (Namespace/WS プロトコル) | [.github/instructions/aituber-csharp.instructions.md](.github/instructions/aituber-csharp.instructions.md) |
| テストアセンブリ・TC-ID 体系 | [.github/instructions/aituber-tests.instructions.md](.github/instructions/aituber-tests.instructions.md) |
| ドキュメント同期ルール | [.github/instructions/sync-docs.instructions.md](.github/instructions/sync-docs.instructions.md) |
| コード変更後の MCP 手順 (Unity) | [.github/instructions/unity-mcp.instructions.md](.github/instructions/unity-mcp.instructions.md) |
| ゴールデン原則（ゴミ収集ルール） | [.github/instructions/golden-principles.instructions.md](.github/instructions/golden-principles.instructions.md) |
| Python orchestrator セットアップ | [AITuber/README.md](AITuber/README.md) |

---

## ハード制約（常に適用）

1. **テストが通ること** — `pytest AITuber/tests/` + Unity EditMode/PlayMode 全グリーン
2. **ruff/black クリーン** — `ruff check AITuber/orchestrator/ AITuber/tests/`
3. **SRS ID 参照** — コード・コミットには関連する FR/NFR/TC ID を記載
4. **シークレット禁止** — `.env` はリポジトリに含めない（`.gitignore` 参照）
5. **ドキュメント同期** — コード変更時は関連ドキュメントを同時更新（sync-docs.instructions.md 参照）

---

## 技術スタック（概要）

| 層 | 技術 | バージョン |
|---|---|---|
| Orchestrator | Python | 3.11+ |
| Avatar | Unity | 6000.3.0f1 / URP |
| WS | WebSocket | port 31900 |
| TTS | VOICEVOX | http://127.0.0.1:50021 |
| Runtime アセンブリ | AITuber.Runtime | autoReferenced: true |
| LLM | OpenAI API | gpt-4o(-mini) |

---

## 現在のマイルストーン状況

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

---

## Done の定義

PR/タスクが完了とみなされる条件:

- [ ] 対象テスト全グリーン（`pytest` + Unity）
- [ ] `ruff check` エラーゼロ
- [ ] 変更した設計はドキュメントに反映済み
- [ ] FR/NFR/TC ID が変更コードに記載済み
- [ ] `QUALITY_SCORE.md` の該当ドメインを更新
- [ ] 技術的負債が発生した場合 `tech-debt-tracker.md` に追記

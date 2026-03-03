# M2: ReflectionRunner exec-plan

> **作成**: 2026-03-03  
> **目標**: GapLogger が収集した Capability Gap JSONL を LLM で解析し、BehaviorPolicy への改善Proposalを自動生成する  
> **関連**: FR 未割当（SRS更新要）, autonomous-growth.md M2, PLANS.md  
> **依存**: M1完了（ActionDispatcher/GapLogger 実装済み、61/61テスト グリーン）

---

## ゴール

配信セッション終了後、`capability_gaps/<stream_id>.jsonl` を読み込み：
1. Gapのパターンを分析する
2. `behavior_policy.yml` の新エントリ案を LLM（LLM-Modulo）が生成する
3. 外部バリデーターがスキーマ・安全性を検証する
4. 人間または自動承認後に `behavior_policy.yml` に追記する

**Done の定義:**
- ReflectionRunner が Gap JSONL を読んで、有効な YAML エントリを少なくとも1件生成できる
- 生成されたエントリが行動テーブルスキーマを満たす（バリデーターが通る）
- 誤ったエントリがポリシーに混入しない（バリデーターが正しく拒否する）
- テストカバレッジ: `TC-REFL-01〜XX` 全グリーン

---

## スコープ

| 含む | 含まない |
|---|---|
| Gap JSONL 読み込みパーサー (Python) | Unity 側の実装変更 |
| LLM プロンプト設計（Gap→Proposal） | モデルのファインチューニング |
| ProposalValidator (スキーマ + 安全チェック) | 自動マージ（M3以降） |
| behavior_policy.yml 追記ロジック | OBS連携 |
| テスト (pytest, モック LLM) | リアルタイム Reflection（バッチ処理のみ） |

---

## 設計決定ログ

### 2026-03-03: LLM-Modulo アーキテクチャを採用

Kambhampati et al. 2024「LLMs Can't Plan」の知見に基づき、LLM 単体での Proposal 生成は採用しない。
LLM が生成した YAML を必ず外部バリデーターが検証する LLM-Modulo パターンを採用する。

**却下した案**: LLM の出力をそのまま policy に追記 → 誤ったアクションが自動実行される危険性

### 2026-03-03: Python 実装（Unity 側は変更なし）

ReflectionRunner は Unity 側を変更せず、Python orchestrator の新モジュールとして実装する。
Gap JSONL はファイルシステム経由でやり取りする（M3 で WebSocket 化を検討）。

---

## タスクブレークダウン

- [ ] `orchestrator/reflection_runner.py` — Gap JSONL 読み込み + LLM 呼び出し
- [ ] `orchestrator/proposal_validator.py` — YAML スキーマ + 安全チェック
- [ ] `orchestrator/policy_updater.py` — behavior_policy.yml 追記
- [ ] Gap JSONL → LLM プロンプトの設計（few-shot 例を含む）
- [ ] `tests/test_reflection_runner.py` — モック LLM で全フロー検証 (TC-REFL-01〜)
- [ ] `tests/test_proposal_validator.py` — Valid/Invalid YAML テスト (TC-REFL-XX〜)
- [ ] SRS に FR-REFL-01 等 追記
- [ ] QUALITY_SCORE.md Growth/ReflectionRunner 行を D→B 更新
- [ ] PLANS.md M2 を完了に更新

---

## 進捗ログ

### 2026-03-03: 計画作成

M1 が 61/61 テスト グリーンで完了。M2 計画を作成した。
Gap JSONL フォーマットは `GapEntry.cs` で確定済み（autonomous-growth.md 参照）。
LLM-Modulo の採用を決定（設計決定ログ参照）。

---

## 完了チェック

- [ ] 全テストグリーン (`pytest AITuber/tests/` + Unity)
- [ ] ruff/black クリーン
- [ ] QUALITY_SCORE.md の Growth/ReflectionRunner 行を更新
- [ ] PLANS.md の M2 を完了に更新、M3 の依存を解除
- [ ] このファイルを `exec-plans/completed/` に移動

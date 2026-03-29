# M30: Memory Quality (Aegis Essence) exec-plan

> **作成**: 2026-03-26  
> **完了**: 2026-03-26  
> **目標**: runtime memory layers に Budget Compiler / Evidence-Linked Facts / Time-Decayed Confidence / Post-Reply Micro-Triage を追加し、長期運用時のコンテクスト品質を向上させる  
> **関連**: PLANS.md M30, ARCHITECTURE.md Runtime Memory Layers  
> **依存**: M26, M27, M28, M29 完了

---

## ゴール

LLM に注入するフラグメントにトークン予算上限を設け、事実に証拠リンク・時間減衰・矛盾検出を導入する。

**Done の定義:**
- fragment assembly にトークン予算上限が適用される (FR-MEM-BUDGET-01)
- SemanticFact に evidence_ids / last_contradicted が記録される (FR-MEM-EVIDENCE-01)
- SemanticFact / GoalEntry の confidence が時間経過で減衰する (FR-MEM-DECAY-01)
- reply 直後に negation signal を検出して contradiction flag を立てる (FR-MEM-TRIAGE-01)
- maintenance CLI が decayed fact/goal を自動 prune する
- 既存テスト 0 regression
- ruff check クリーン

---

## スコープ

| 含む | 含まない |
|---|---|
| `memory_budget.py` — トークン予算コンパイラ | embedding ベース retrieval |
| `micro_triage.py` — 矛盾検出 | LLM-based contradiction resolution |
| SemanticFact に evidence_ids / last_contradicted 追加 | vector DB migration |
| GoalEntry に effective_confidence 追加 | runtime prompt path の大規模再設計 |
| episodic freshness floor 0.7→0.3 | recall scorer アルゴリズム変更 |
| maintenance CLI に decayed prune 追加 | auto-maintenance scheduling |

---

## 設計決定ログ

### 2026-03-26: Budget Compiler はヒューリスティックトークン推定

tiktoken 等の外部依存を避け、JP は ~1 token/char、EN は ~4 chars/token のヒューリスティックで推定する。
フラグメント優先度は `[WORLD]` > `[FACTS]` > `[GOALS]` > `[MEMORY]` の固定順。

### 2026-03-26: Micro-Triage は negation signal のパターンマッチ

LLM 再呼び出しのコスト・レイテンシを避け、日本語・英語の negation キーワード ("嫌い", "飽きた", "もういい", "やめた", "hate", "bored", "quit" 等) による lexical detection に限定。

### 2026-03-26: Time-Decay は maintenance prune と prompt sort の両方に適用

SemanticFact は 30 日半減期、GoalEntry は 21 日半減期。
`effective_confidence(now) < 0.10` の fact/goal は maintenance run で自動 prune。
prompt fragment sort にも effective_confidence を使い、古い情報が自然に下位へ落ちる。

### 2026-03-26: Episodic freshness floor を 0.7→0.3 に引き下げ

古いエピソードの重みが高止まりしていた問題 (最低 0.7) を修正。
新 floor 0.3 により、古い episode は recall ranking で効果的に沈む。

---

## タスクブレークダウン

- [x] `memory_budget.py` 追加 (FR-MEM-BUDGET-01)
- [x] `micro_triage.py` 追加 (FR-MEM-TRIAGE-01)
- [x] SemanticFact に evidence_ids / last_contradicted / effective_confidence 追加 (FR-MEM-EVIDENCE-01, FR-MEM-DECAY-01)
- [x] GoalEntry に effective_confidence 追加 (FR-MEM-DECAY-01)
- [x] episodic freshness floor 0.7→0.3 (FR-MEM-DECAY-01)
- [x] main.py に budget compiler 統合
- [x] main.py に micro-triage 統合
- [x] maintenance CLI に decayed prune 追加
- [x] テスト追加 (24 新規: TC-MEM-BUDGET-01〜05, TC-MEM-TRIAGE-01〜04, TC-MEM-EVIDENCE-01〜03, TC-MEM-DECAY-01〜04, TC-M30-MAINT-01〜03)
- [x] 全 72 テスト green (24 新規 + 48 既存 memory 関連)
- [x] ruff check クリーン
- [x] exec-plan 作成
- [x] QUALITY_SCORE.md 更新

---

## テストケース

| TC ID | 内容 | ファイル |
|---|---|---|
| TC-MEM-BUDGET-01 | 空文字列は 0 トークン | test_memory_budget.py |
| TC-MEM-BUDGET-02 | 英語テキスト推定 | test_memory_budget.py |
| TC-MEM-BUDGET-03 | 日本語テキスト推定 | test_memory_budget.py |
| TC-MEM-BUDGET-04 | 予算上限で切り詰め | test_memory_budget.py |
| TC-MEM-BUDGET-05 | 優先度順で WORLD > MEMORY | test_memory_budget.py |
| TC-MEM-TRIAGE-01 | negation なしで contradiction 0 | test_micro_triage.py |
| TC-MEM-TRIAGE-02 | negation signal で既存 interest flag | test_micro_triage.py |
| TC-MEM-TRIAGE-03 | topic 不一致なら flag しない | test_micro_triage.py |
| TC-MEM-TRIAGE-04 | 空テキストは 0 | test_micro_triage.py |
| TC-MEM-EVIDENCE-01 | observe が episode_id を保存 | test_memory_quality.py |
| TC-MEM-EVIDENCE-02 | evidence_ids 後方互換 | test_memory_quality.py |
| TC-MEM-EVIDENCE-03 | evidence_ids serde roundtrip | test_memory_quality.py |
| TC-MEM-DECAY-01 | 新しい fact は confidence 維持 | test_memory_quality.py |
| TC-MEM-DECAY-02 | 古い fact は大幅減衰 | test_memory_quality.py |
| TC-MEM-DECAY-03 | contradicted fact は半減 | test_memory_quality.py |
| TC-MEM-DECAY-04 | goal effective_confidence 減衰 | test_memory_quality.py |
| TC-M30-MAINT-01 | maintenance が decayed fact を prune | test_maintenance_decay.py |
| TC-M30-MAINT-02 | fresh fact は維持 | test_maintenance_decay.py |
| TC-M30-MAINT-03 | report に decay count 含む | test_maintenance_decay.py |

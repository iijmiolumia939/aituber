# M27: Semantic Memory Layer exec-plan

> **作成**: 2026-03-14  
> **完了**: 2026-03-14  
> **目標**: repeated interactions から runtime durable facts を抽出し、viewer familiarity と repeated topic interest を prompt に注入できるようにする  
> **関連**: FR-MEMORY-SEM-01, PLANS.md M27, autonomous-growth.md Runtime Memory Layers  
> **依存**: M26 完了

---

## ゴール

transcript をそのまま増やさず、反復する関係性や話題を compact facts として扱う。

**Done の定義:**
- `semantic_memory.py` が file-backed durable fact store として動作する
- reply path に `[FACTS]` block が注入される
- repeated viewer interaction が familiarity fact を更新する
- repeated topics が viewer interest fact に昇格する
- tests と changed-files quality gate が通る

---

## スコープ

| 含む | 含まない |
|---|---|
| viewer familiarity facts | unresolved promises |
| repeated topic facts | goal memory |
| reply path への `[FACTS]` 注入 | embeddings |
| semantic memory unit tests | contradiction checker |

---

## 設計決定ログ

### 2026-03-14: 初期 M27 は viewer familiarity + repeated topics に限定

semantic memory を一気に広げると fact extraction の品質評価が難しくなる。
まずは高 ROI で deterministic test を書きやすい viewer familiarity と repeated topic interest に限定する。

### 2026-03-14: transcript 再注入ではなく compact fact prompt を採用

semantic memory の価値は context length 拡大ではなく durable state の保持にある。
そのため `[FACTS]` block は短い自然文の列にし、transcript の再掲は行わない。

---

## タスクブレークダウン

- [x] `orchestrator/semantic_memory.py` 新設
- [x] viewer familiarity 更新ロジック実装
- [x] repeated topic fact 抽出実装
- [x] `main.py` reply path へ `[FACTS]` 注入
- [x] `tests/test_semantic_memory.py` 新設
- [x] `tests/test_orchestrator.py` に integration tests 追加
- [x] targeted pytest + changed-files quality gate
- [x] 必要なら prompt shaping を微調整

---

## 進捗ログ

### 2026-03-14

初期版の `SemanticMemory` を追加し、viewer familiarity と repeated topic interest を JSONL-backed facts として保持できる状態にした。
reply path では `[WORLD]` + `[FACTS]` + `[MEMORY]` の順で LLM context を組み立てる構成に変更した。
その後、`[FACTS]` の phrasing を transcript 再掲ではない自然文に寄せ、narrative 用 overview fragment も追加した。

---

## 完了チェック

- [x] 全テストグリーン
- [x] ruff/black クリーン
- [x] changed-files quality gate 通過
- [x] PLANS.md 更新
- [x] autonomous-growth.md 更新

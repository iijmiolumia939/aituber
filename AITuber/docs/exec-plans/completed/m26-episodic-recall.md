# M26: Episodic Recall Engine exec-plan

> **作成**: 2026-03-14  
> **完了**: 2026-03-14  
> **目標**: runtime episodic memory を会話ログから metadata-aware recall engine に拡張し、行動結果も記憶に取り込めるようにする  
> **関連**: FR-E2-01, FR-E2-02, PLANS.md M26, autonomous-growth.md Runtime Memory Layers  
> **依存**: M25 完了

---

## ゴール

会話履歴を単なる transcript ではなく runtime recall engine として扱う。

**Done の定義:**
- `EpisodeEntry` が runtime metadata を保持できる
- `behavior_completed` 成功/失敗が episodic memory に記録される
- recall 順位が freshness / access_count / viewer continuity / time bucket に反応する
- old JSONL が後方互換で読み込める
- targeted pytest と changed-files quality gate が通る

---

## スコープ

| 含む | 含まない |
|---|---|
| `episodic_store.py` metadata 拡張 | semantic memory 抽出 |
| 複合 recall scorer | embedding / vector DB |
| `_on_perception_update` の behavior completion ingestion | goal memory |
| reply path の viewer-aware recall | contradiction checker |

---

## 設計決定ログ

### 2026-03-14: forgetting は削除でなく retrieval-side decay を採用

MemoryBank の忘却曲線は有用だが、初期段階での物理削除はデバッグ性を損なうため不採用。
古い記憶は削除せず、`freshness_factor` によって想起順位を下げる方針にした。

### 2026-03-14: viewer continuity を first-class signal とする

配信体験上の価値は「長大文脈」より「同じ視聴者への継続性」にある。
そのため recall scorer に `author` / `related_viewer` 一致ブーストを明示的に入れた。

---

## タスクブレークダウン

- [x] `EpisodeEntry` に metadata を追加
- [x] `EpisodicStore.get_relevant()` を複合 scorer に変更
- [x] access reinforcement (`last_accessed`, `access_count`) を追加
- [x] `behavior_completed` 成功/失敗を episodic memory に保存
- [x] `tests/test_episodic_store.py` に M26 ケース追加
- [x] `tests/test_orchestrator.py` に ingestion ケース追加
- [x] targeted pytest 実行
- [x] changed-files quality gate 通過

---

## 進捗ログ

### 2026-03-14

`episodic_store.py` を metadata-aware に拡張し、reply path と perception loop の両方から runtime events を記録するようにした。
実装中に `_reply_to()` が first sentence を二重連結して episodic memory に誤った全文を書き込む不具合を発見し、同時に修正した。

---

## 完了チェック

- [x] 全テストグリーン（targeted pytest）
- [x] ruff/black クリーン
- [x] changed-files quality gate 通過
- [x] PLANS.md 更新
- [x] autonomous-growth.md 更新

# M29: Runtime Memory Maintenance exec-plan

> **作成**: 2026-03-14  
> **完了**: 2026-03-14  
> **目標**: runtime memory layers を配信後バッチで安全に整理し、長期運用時の drift と JSONL 肥大化を抑える  
> **関連**: PLANS.md M29, autonomous-growth.md Runtime Memory Layers  
> **依存**: M26, M27, M28 完了

---

## ゴール

reply path や scheduler path を変更せず、persisted JSONL に対する maintenance を後処理として導入する。

**Done の定義:**
- dry-run で maintenance 差分を inspect できる
- duplicate episode burst を merge できる
- stale low-signal episode を archive に退避できる
- archived episode から missing semantic facts / goals を保守的に backfill できる
- old JSONL schema を壊さない
- targeted pytest と changed-files quality gate が通る

---

## スコープ

| 含む | 含まない |
|---|---|
| `memory_maintenance_cli.py` 追加 | runtime recall scorer の再設計 |
| duplicate merge / stale archival | vector DB / embedding migration |
| archived episode からの conservative semantic/goal promotion | aggressive fact reweighting |
| dry-run / apply の inspectable report | runtime prompt path への同期 hook |

---

## 設計決定ログ

### 2026-03-14: maintenance は runtime path ではなく CLI に分離

reply latency と scheduler 安定性を守るため、maintenance は `memory_maintenance_cli.py` に閉じ込め、配信後に手動またはタスク経由で回す方針にした。

### 2026-03-14: promotion は re-count でなく missing entry backfill に限定

既存 semantic / goal entry を maintenance が再集計で上書きすると continuity の重みが意図せず変化する。
そのため archived episode からの promotion は「まだ存在しない durable fact / goal だけを足す」保守的モードに限定した。

---

## タスクブレークダウン

- [x] `memory_maintenance_cli.py` 追加
- [x] duplicate episode burst merge 実装
- [x] stale low-signal archive 実装
- [x] archived episode から semantic backfill 実装
- [x] archived episode から goal backfill 実装
- [x] old JSONL compatibility テスト追加
- [x] targeted pytest 実行
- [x] changed-files quality gate 通過

---

## 進捗ログ

### 2026-03-14

`memory_maintenance_cli.py` を新設し、`--dry-run` / `--json` / `--archive` を持つ inspectable maintenance を導入した。
episode 側は normalized user text と response containment を使って burst duplicate を merge し、古くて low-signal かつ未参照の non-conversation / non-viewer episode だけを archive に退避する。
archive 済み episode からは、未登録の viewer profile / viewer interest / topic goal だけを backfill するため、既存 continuity の重みを乱さずに long-tail context を圧縮できる。
また apply 時の書き込みは active episodic store を最後に atomic replace する順序へ変更し、archive や durable layer への保存失敗で唯一の episode copy を失わないようにした。

---

## 完了チェック

- [x] 全テストグリーン（targeted pytest）
- [x] ruff/black クリーン
- [x] changed-files quality gate 通過
- [x] PLANS.md 更新
- [x] autonomous-growth.md 更新
- [x] QUALITY_SCORE.md 更新
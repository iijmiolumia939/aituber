# M6 実行計画: 人間承認フロー (BehaviorPolicy 自律拡張 Phase 2)

> **作成**: 2026-03-04  
> **担当**: AI Agent  
> **依存**: M5 完了 (reflection_cli.py / TD-010 解消)  
> **目標**: LLM提案 → 人間承認 → policy 自動マージ の End-to-End フロー完成 (Phase 2)

---

## 問題と目標

### 現状 (M5 完了後)

```
GapDashboard → ReflectionRunner → ProposalValidator → PolicyUpdater
                                                           ↑
                                                  --dry-run か直書きのみ
```

Phase 1 では「人間が手動実装」だったが、
Phase 2 では **LLM 提案を人間がレビューして承認 → 自動マージ** できなければならない。

現在の `reflection_cli --dry-run` は提案を表示するだけで staging しない。

### M6 ゴール

```
reflection_cli --output proposals_staging.yml
    → proposals_staging.yml  (staging ファイル)
           ↓
approve_cli --staging proposals_staging.yml --policy behavior_policy.yml
    → 対話型 y/n レビュー
    → 承認分だけ behavior_policy.yml に追記
```

---

## 実装スコープ

### 1. `reflection_cli.py` に `--output` フラグ追加

```
--output YAML   提案を behavior_policy.yml に直書きせず指定ファイルへ staging する
                (--dry-run と組み合わせ不可; --output 指定時は policy 書き込みをスキップ)
```

`ReflectionCLI` に `output_path: str | None = None` パラメータを追加。
`output_path` が指定された場合、valid proposals を YAML リストとして書き出す。

### 2. `orchestrator/approve_cli.py` (新規)

```
python -m orchestrator.approve_cli [options]

--staging YAML      staging ファイルパス (default: proposals_staging.yml)
--policy YAML       behavior_policy.yml パス (default: Assets/StreamingAssets/behavior_policy.yml)
--auto-approve      全提案を自動承認 (CI/テスト用)
--auto-reject       全提案を自動却下 (テスト用)
```

パイプライン:
1. `proposals_staging.yml` を読み込む
2. 各提案を表示 (intent / cmd / gesture / notes)
3. stdin から `y/n/q` を受け取る (`--auto-approve` 時はスキップ)
4. 承認された提案を `PolicyUpdater.append_entries()` で policy に追記
5. 処理済みの提案を staging ファイルから削除 (or ファイルを空にする)
6. 追記数・却下数をサマリー表示

### 3. `ApproveCLI` クラス設計

```python
class ApproveCLI:
    def __init__(
        self,
        staging_path: str,
        policy_path: str,
        auto_approve: bool = False,
        auto_reject: bool = False,
        input_fn: Callable[[str], str] | None = None,  # テスト用 DI
    ): ...

    def run(self) -> int: ...  # exit code
```

`input_fn` を DI することでテストでの stdin モックが不要になる。

---

## テストケース (TDD 先行)

### `tests/test_approve_cli.py`

| TC ID | 内容 |
|---|---|
| TC-M6-01 | staging ファイルが存在しない → 終了コード 0、policy 未変更 |
| TC-M6-02 | staging ファイルが空 → 終了コード 0、policy 未変更 |
| TC-M6-03 | `--auto-approve` → 全提案が policy に追記される |
| TC-M6-04 | `--auto-reject` → 全提案が却下、policy 未変更 |
| TC-M6-05 | 対話型 y/n → y の提案のみ policy に追記 |
| TC-M6-06 | 承認後 staging ファイルがクリアされる |
| TC-M6-07 | `build_parser()` デフォルト値検証 |

### `tests/test_reflection_cli.py` 追加ケース

| TC ID | 内容 |
|---|---|
| TC-M6-08 | `--output` 指定 → staging.yml に提案が書き込まれる |
| TC-M6-09 | `--output` + valid proposal → behavior_policy.yml は変更されない |

---

## SRS ID

- `FR-APPR-01`: staging ファイルへの提案出力
- `FR-APPR-02`: 対話型承認 CLI (`approve_cli`)
- `FR-APPR-03`: `--auto-approve` フラグ (CI モード)

---

## Done 判定

- [x] TC-M6-01〜09 全グリーン (14/14 TC)
- [x] `ruff check` クリーン
- [x] `AGENTS.md` / `PLANS.md` / `QUALITY_SCORE.md` / `tech-debt-tracker.md` 更新済み
- [x] `autonomous-growth.md` M6 完了マーク
- [x] `exec-plans/active/ → completed/` 移動
- [x] `aituber-tests.instructions.md` TC-M6-xx 追記
- [x] `git commit && git push`

---

## 進捗ログ

| 日時 | 内容 |
|---|---|
| 2026-03-04 | exec-plan 作成 |
| 2026-03-04 | TDD: test_approve_cli.py (TC-M6-01〜07) + test_reflection_cli.py TC-M6-08〜11 作成 |
| 2026-03-04 | approve_cli.py 実装完了 (ApproveCLI + build_parser + main) |
| 2026-03-04 | reflection_cli.py に --output フラグ追加 (_write_staging メソッド) |
| 2026-03-04 | 14/14 TC グリーン、ruff クリーン、全スイート 340 passed |
| 2026-03-04 | **完了** — commit pushed |

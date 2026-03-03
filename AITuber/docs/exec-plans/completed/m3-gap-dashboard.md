# M3: GapDashboard exec-plan

> **作成**: 2026-03-03  
> **目標**: GapLogger が収集した Capability Gap JSONL を集計・可視化し、上位 Gap を特定する CLI ツールを実装  
> **関連**: autonomous-growth.md M3, PLANS.md  
> **依存**: M1完了（GapLogger — JSONL 出力）、M2完了（ReflectionRunner — ProposalValidator/PolicyUpdater）

---

## ゴール

配信セッション後（または任意のタイミング）に：
1. `Logs/capability_gaps/` 以下の全 JSONL を集計する
2. カテゴリ別・intent 別の Gap 頻度を集計する
3. `priority_score` を頻度ベースで自動算出する（TD-011 解消）
4. コンソールに Rich テーブルで表示する
5. `--top N` オプションで上位 N 件を返す

**Done の定義:**
- `gap_dashboard.py` として実装、`python -m orchestrator.gap_dashboard` で動作
- テストカバレッジ: `TC-DASH-01〜XX` 全グリーン
- `priority_score` 算出式 TD-011 を解消

---

## スコープ

| 含む | 含まない |
|---|---|
| JSONL 集計（カテゴリ別・intent別） | GitHub Issue 自動作成（M4以降） |
| priority_score 算出（頻度ベース） | Web UI / グラフ描画 |
| Rich テーブル表示 | VOICEVOX / OBS 連携 |
| `--top N` / `--category` フィルタ | リアルタイム監視 |
| テスト (pytest) | Unity 側変更 |

---

## 設計決定ログ

### 2026-03-03: orchestrator/ に配置

`tools/gap_dashboard.py` より `orchestrator/gap_dashboard.py` の方が:
- 既存の `ReflectionRunner` / `PolicyUpdater` を直接 import できる
- `pytest AITuber/tests/` の発見対象に自動的に入る

### 2026-03-03: priority_score 算出式 (TD-011 解消)

```
priority_score = (発生頻度 / 総Gap数) × (1 / cost_weight[gap_category])
```

`cost_weight`:
| gap_category | weight | 理由 |
|---|---|---|
| missing_motion | 1.0 | 比較的容易（YAML 5行） |
| missing_behavior | 1.5 | 中程度（WS protocol 10行） |
| missing_integration | 3.0 | 難（新機能実装） |
| capability_limit | 5.0 | 非常に難（C# + WS拡張） |
| environment_limit | 4.0 | 難（Asset追加） |
| unknown | 2.0 | デフォルト |

---

## タスクブレークダウン

- [ ] `tests/test_gap_dashboard.py` — TC-DASH-01〜XX (TDD: 先行作成)
- [ ] `orchestrator/gap_dashboard.py` — 集計・スコア算出・Rich 出力
- [ ] SRS に FR-DASH-01〜02 追記
- [ ] QUALITY_SCORE.md Growth/GapDashboard 行追加
- [ ] PLANS.md M3 完了に更新
- [ ] tech-debt-tracker.md TD-011 を解消済みに更新

---

## 進捗ログ

### 2026-03-03: 計画作成

M1/M2 完了後に M3 開始。autonomous-growth.md のマイルストーン定義に従って GapDashboard CLI を実装する。

---

## 完了チェック

- [ ] 全テストグリーン (`pytest AITuber/tests/test_gap_dashboard.py`)
- [ ] ruff/black クリーン
- [ ] `python -m orchestrator.gap_dashboard --help` が動作
- [ ] QUALITY_SCORE.md 更新
- [ ] PLANS.md M3 完了に更新
- [ ] tech-debt-tracker.md TD-011 解消
- [ ] このファイルを `exec-plans/completed/` に移動

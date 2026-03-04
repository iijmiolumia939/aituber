# M4 Exec-Plan: 上位 Gap 手動実装（初回成長）

> **ステータス**: 🔧 実装中 (2026-03-04 着手)  
> **依存**: M3 GapDashboard ✅ 完了  
> **SRS refs**: FR-GROW-01（将来追記予定）

---

## 目的

GapDashboard によって集計された上位 N 件の missing_intent を
`behavior_policy.yml` に追加する（Phase 1: 人間が手動で実装）。

Phase 1 のフロー:

```
Logs/capability_gaps/*.jsonl
     │
     ▼ GapDashboard (M3)
  top 5 intents by priority_score
     │
     ▼ 人間レビュー (コスト・実現性確認)
  M4: behavior_policy.yml へ追記
     │
     ▼ ActionDispatcher (M1)
  次回配信で Gap が解消 → GapLogger が記録しなくなる
```

---

## 方針

- **実データが存在しない** 開発環境では、リアルなギャップを模したフィクスチャ JSONL を
  `tests/fixtures/sample_gaps/` に配置し、GapDashboard を当てる
- フィクスチャのギャップは配信コンテキスト上ありうるコメント（"拍手して" 等）から設計する
- 実装目標: `missing_motion` / `missing_expression` 上位 7 件を `behavior_policy.yml` に追加

---

## フィクスチャ設計

ファイル: `tests/fixtures/sample_gaps/stream_20260303.jsonl`

| intent | gap_category | 件数 | cost_weight | 期待スコア |
|---|---|---|---|---|
| `clap_hands` | missing_motion | 12 | 1.0 | 最高 |
| `thumbs_up` | missing_motion | 9 | 1.0 | 2位 |
| `express_embarrassed` | missing_expression | 8 | 1.0 | 3位 |
| `laugh_out_loud` | missing_motion | 6 | 1.0 | 4位 |
| `point_at_camera` | missing_motion | 5 | 1.0 | 5位 |
| `spin_360` | missing_motion | 4 | 1.0 | 6位 |
| `express_sleepy` | missing_expression | 3 | 1.0 | 7位 |
| `sing_intro` | capability_limit | 10 | 5.0 | コスト高・低スコア |
| `dance_move` | capability_limit | 8 | 5.0 | コスト高・低スコア |

総 Gap 数: 65 件 (stream_20260303)

---

## タスクブレークダウン

- [x] PLANS.md に M4 追記・アクティブ化
- [x] `tests/fixtures/sample_gaps/stream_20260303.jsonl` 作成
- [x] `tests/test_m4_policy_growth.py` 作成 (TC-M4-01〜08, TDD先行)
- [x] `behavior_policy.yml` に 7 エントリ追記
- [x] テスト全グリーン / ruff クリーン
- [ ] SRS 更新（FR-GROW-01 追記 → M4 はデータ追記タスクのため省略可）
- [x] docs 更新・commit/push
- [ ] post-M4 フロー実行

---

## 追加する behavior_policy.yml エントリ

```yaml
# ── M4: Gestures identified by GapDashboard top-5 ──────────────────────────
- intent: clap_hands
  cmd: avatar_update
  gesture: clap
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-1 missing_motion"

- intent: thumbs_up
  cmd: avatar_update
  gesture: thumbs_up
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-2 missing_motion"

- intent: laugh_out_loud
  cmd: avatar_update
  gesture: laugh
  emotion: happy
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-4 missing_motion"

- intent: point_at_camera
  cmd: avatar_update
  gesture: point_forward
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-5 missing_motion"

- intent: spin_360
  cmd: avatar_update
  gesture: spin
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-6 missing_motion"

# ── M4: Expressions identified by GapDashboard top-5 ────────────────────────
- intent: express_embarrassed
  cmd: avatar_update
  emotion: embarrassed
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-3 missing_expression"

- intent: express_sleepy
  cmd: avatar_update
  emotion: sleepy
  priority: 0
  notes: "TC-M4-06 / FR-GROW-01: GapDashboard top-7 missing_expression"
```

---

## テストケース一覧

| TC ID | 内容 |
|---|---|
| TC-M4-01 | sample fixture → GapDashboard top intent = `clap_hands` |
| TC-M4-02 | top-5 intents はすべて `missing_motion` または `missing_expression` |
| TC-M4-03 | capability_limit (`sing_intro`) は top-5 に入らない（cost_weight=5.0） |
| TC-M4-04 | GapDashboard `--category missing_motion` で `clap_hands` が首位 |
| TC-M4-05 | build_summary の total_gaps が期待値と一致 |
| TC-M4-06 | behavior_policy.yml に `clap_hands` 等 7 intent が存在する |
| TC-M4-07 | 新エントリが ProposalValidator.validate() で VALID |
| TC-M4-08 | PolicyUpdater.load_policy() で新エントリが正しくロードされる |

---

## 完了ログ

- **2026-03-04**: 実装完了
  - `tests/fixtures/sample_gaps/stream_20260303.jsonl` — 65 Gap entries (9 intents)
  - `tests/test_m4_policy_growth.py` — TC-M4-01〜08, **24/24 グリーン**, ruff クリーン
  - `behavior_policy.yml` — 7 新エントリ追加 (clap_hands, thumbs_up, express_embarrassed, laugh_out_loud, point_at_camera, spin_360, express_sleepy)
  - 全テストスイート 315+ / 2 pre-existing failures のみ（M4由来ゼロ）


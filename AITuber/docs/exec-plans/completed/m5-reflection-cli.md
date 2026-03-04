# M5 Exec-Plan: ReflectionRunner end-to-end 配線 (TD-010 解消)

> **ステータス**: 🔧 実装中 (2026-03-04 着手)  
> **依存**: M4 完了 ✅  
> **SRS refs**: FR-REFL-01, FR-REFL-02, FR-REFL-03, FR-REFL-04  
> **解消**: TD-010 (ReflectionRunner backend wiring 未整備)

---

## 目的

M2 で実装した ReflectionRunner は `backend=None` のまま電話が繋がっていない状態だった。  
M5 では `orchestrator/reflection_cli.py` を実装し、以下の end-to-end パイプラインを完成させる:

```
Logs/capability_gaps/*.jsonl
     │ GapDashboard.load_all_gaps() + get_top_gaps()
     ▼
ReflectionRunner.generate_proposals(gaps)
  └─ OpenAIBackend.chat()  ← llm_client.py の既存実装を注入
     │
     ▼ LLM-Modulo Validator
ProposalValidator.validate(proposal) for each proposal
     │
     ▼ (VALID only)
PolicyUpdater.append_entries(policy_yml, valid_entries)
```

`--dry-run` フラグで PolicyUpdater への書き込みをスキップできる（安全設計）。

---

## 再利用コンポーネント（新規作成不要）

| コンポーネント | ファイル | 役割 |
|---|---|---|
| `LLMBackend` (Protocol) | `llm_client.py` | backend インタフェース |
| `OpenAIBackend` | `llm_client.py` | 実 OpenAI 呼び出し |
| `ReflectionRunner` | `reflection_runner.py` | Gap → Proposal |
| `ProposalValidator` | `proposal_validator.py` | 5層 Validation |
| `PolicyUpdater` | `policy_updater.py` | YAML 追記 |
| `GapDashboard` | `gap_dashboard.py` | Gap 集計 + Top-N 抽出 |

---

## 新規実装: `orchestrator/reflection_cli.py`

```python
async def run(args) → int:
    # 1. Load + deduplicate gaps via GapDashboard
    # 2. Get top-N unique intents
    # 3. Inject OpenAIBackend → ReflectionRunner
    # 4. generate_proposals(top_gaps)
    # 5. validate each proposal
    # 6. if not dry-run: append_entries
    # 7. print summary
    return 0

def main(argv=None) → int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run(args))
```

CLI flags:
- `--gaps-dir` (default: `Logs/capability_gaps`)
- `--policy` (default: `Assets/StreamingAssets/behavior_policy.yml`)
- `--top-n` (default: 5)
- `--dry-run` (flag, default off)
- `--model` (default: from env `OPENAI_API_KEY` / `gpt-4o-mini`)

---

## タスクブレークダウン

- [x] PLANS.md M5 アクティブ化
- [ ] `tests/test_reflection_cli.py` 作成 (TC-M5-01〜08, TDD先行)
- [ ] `orchestrator/reflection_cli.py` 作成
- [ ] テスト全グリーン / ruff クリーン
- [ ] SRS — FR-REFL-05 (end-to-end CLI) 追記
- [ ] tech-debt-tracker TD-010 解消済みに移動
- [ ] docs 更新・commit/push
- [ ] post-M5 フロー

---

## テストケース一覧

| TC ID | 内容 |
|---|---|
| TC-M5-01 | `gaps_dir` が存在しない → 標準エラー出力してリターンコード 0 |
| TC-M5-02 | gaps が空 → リターンコード 0、policy 未変更 |
| TC-M5-03 | mock backend が valid YAML → proposals 生成される |
| TC-M5-04 | mock backend が invalid YAML → proposals = 0件 |
| TC-M5-05 | `dry_run=True` → PolicyUpdater.append_entries が呼ばれない |
| TC-M5-06 | `dry_run=False` + valid proposal → policy file に追記 |
| TC-M5-07 | backend が例外送出 → proposals = 0件、CLI は 0 で終了 |
| TC-M5-08 | `--top-n 3` → 最大 3 gap を LLM に渡す |

---

## 完了ログ

_（実装完了後に記録）_

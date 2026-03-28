# AGENTS.md — AITuber リポジトリ エントリポイント

> **マップであり百科事典ではない。** 詳細は各ポインタ先を参照。

## システム概要

YouTube Live コメント → Orchestrator (Python) → Unity Avatar (C#) の自律配信基盤。
詳細は [ARCHITECTURE.md](ARCHITECTURE.md) を参照。

## ポインタ一覧

| 知りたいこと | 参照先 |
|---|---|
| アーキテクチャ・依存ルール | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 機能要件 (FR/NFR/TC) | [AITuber/.github/srs/](AITuber/.github/srs/) |
| 品質グレード | [QUALITY_SCORE.md](QUALITY_SCORE.md) |
| バグ・負債管理 (**SSoT**) | [GitHub Issues](https://github.com/iijmiolumia939/aituber/issues) |
| 実装計画 | [PLANS.md](PLANS.md) |
| 実行計画 (進捗ログ) | [AITuber/docs/exec-plans/](AITuber/docs/exec-plans/) |
| 設計ドキュメント | [AITuber/docs/design-docs/index.md](AITuber/docs/design-docs/index.md) |
| 技術的負債 Index | [AITuber/docs/tech-debt-tracker.md](AITuber/docs/tech-debt-tracker.md) |
| Copilot ハーネス ADR | [AITuber/docs/adr/0001-github-copilot-harness.md](AITuber/docs/adr/0001-github-copilot-harness.md) |
| Python orchestrator セットアップ | [AITuber/README.md](AITuber/README.md) |
| マイルストーン (M1-M29 全完了) | [MILESTONES.md](MILESTONES.md) |

## ハード制約

1. **テスト全グリーン** — `pytest AITuber/tests/` + Unity EditMode/PlayMode
2. **ruff check クリーン** — `ruff check AITuber/orchestrator/ AITuber/tests/`
3. **FR/NFR/TC ID** をコード・コミットに記載
4. **シークレット禁止** — `.env` は `.gitignore`
5. **ドキュメント同期** — コード変更時に関連ドキュメントも更新
6. **Issue 管理は GitHub Issues 一元** — `gh issue create` で登録、解決時は close

## Done の定義

上記ハード制約 + `QUALITY_SCORE.md` 該当ドメイン更新 + 負債発生時は `tech-debt-tracker.md` 追記。

<!-- aegis:start -->
> 実装・質問とも `aegis_compile_context` を必ず呼ぶこと。
<!-- aegis:end -->

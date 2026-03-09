---
applyTo: "**/*.cs,AITuber/orchestrator/**/*.py,AITuber/tests/**/*.py"
---

# ゴールデン原則 — コードベース一貫性ルール

> Harness Engineering の「garbage collection」アプローチに基づく。  
> これらのルールはエージェントが毎回機械的に守るべき原則。  
> コードの美的好みではなく、エージェントが将来のランで正しく推論できるための基盤。

---

## 原則 1: 共有ユーティリティを優先する（hand-rolled helper 禁止）

- 同じロジックが2箇所に出現したら、共通ユーティリティに抽出する
- 手書きヘルパーを作る前に `orchestrator/` 内の既存モジュールを確認する
- C# では `AITuber.Runtime` アセンブリ内の既存クラスを確認する

---

## 原則 2: 境界でバリデーション、内部では型を信頼する

- 受信点（WSメッセージ受取・外部入力）で一度だけバリデーションする
- 内部関数では null チェック・型再検証を繰り返さない

---

## 原則 3: シークレットをコードに書かない（絶対禁止）

- APIキー・パスワード・OAuth トークンは `.env` / `config/` からのみ読む
- ハードコードされた URL・ポート番号は `config.py` / 設定ファイルに外出し
- ログ出力にパラメーター全体をダンプしない（センシティブなフィールドを除外）

---

## 原則 4: SRS ID を参照する（トレーサビリティ）

変更するコードに関連する FR/NFR/TC ID をコメントまたは docstring に記載する。

```python
# FR-RL-01: ε-greedy による行動選択
def select_action(self, state: str) -> str:
    ...
```

```csharp
// TC-ADSP-01: ポリシーヒット時に Executed を返す
public DispatchResult Dispatch(AvatarIntentParams p) { ... }
```

IDが不明な場合は `.github/srs/requirements.yml` を確認する。

---

## 原則 5: テストなければコードなし

- 新機能を実装する前にテストを書く（TDD）
- Python: `AITuber/tests/test_<module>.py` に追加
- C#: `Assets/Tests/EditMode/` または `Assets/Tests/PlayMode/` に追加
- TC ID を `AITuber/docs/m*-design.md` に追記する
- テストが書けない場合は `tech-debt-tracker.md` に記録する

---

## 原則 6: ドキュメントはコードと同時に更新する

コードを変更したら同じ PR で：
- 影響するドキュメント（docs/*.md）を更新
- `QUALITY_SCORE.md` の関連ドメインのグレード/テスト集計を更新
- 技術的負債が増えた場合は `tech-debt-tracker.md` に追記
- `AGENTS.md` が指すリンクが正しいか確認

---

## 原則 8: Issue 管理は GitHub Issues を Single Source of Truth にする

- 「BUG」「技術的負債」「機能要期」はすべて `gh issue create` で GitHub Issue として登録する
- ローカルドキュメント（`tech-debt-tracker.md`、`PLANS.md`）は Issue 番号へのリンクのみを持つ。詳細決して Issue 側に書く
- 解溈時は `gh issue close` で close する。ローカルドキュメントの記載は「解消済み」に移動する
diff:
  - 重複管理しない: 同じ情報を Issue とローカル両方に書かない
  - PowerShell から楽書きする時はボディを必ずファイル経由で渡す（`--body-file`）。インライン文字列に日本語やバッククォートを含めると文字化けする
  - ファイルは `[System.IO.File]::WriteAllText(path, body, UTF8)` で作成すると安全

---

## 原則 7: エラーメッセージは修正ヒントを含む

「何が間違っているか」だけでなく「どのファイルを修正すべきか」までメッセージに含める。

C# 例: `[BehaviorPolicyLoader] intent='X' not found. Add entry to StreamingAssets/behavior_policy.yml`  
Python 例: `Unknown safety level 'X'. Valid: NG, GRAY, OK. See .github/srs/safety.yml`

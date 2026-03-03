---
applyTo: "**/*.cs,AITuber/orchestrator/**/*.py,AITuber/tests/**/*.py"
---

# ゴールデン原則 — コードベース一貫性ルール

> Harness Engineering の「garbage collection」アプローチに基づく。  
> これらのルールはエージェントが毎回機械的に守るべき原則。  
> コードの美的好みではなく、エージェントが将来のランで正しく推論できるための基盤。

---

## 原則 1: 共有ユーティリティを優先する（hand-rolled helper 禁止）

```
# ❌ やってはいけない
def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))

# ✅ 既存のユーティリティを使う
import math
result = max(0.0, min(1.0, value))
```

- 同じロジックが2箇所に出現したら、共通ユーティリティに抽出する
- 手書きヘルパーを作る前に `orchestrator/` 内の既存モジュールを確認する
- C# では `AITuber.Runtime` アセンブリ内の既存クラスを確認する

**違反の影響**: バグ修正が一方にしか適用されず、もう一方が腐る。

---

## 原則 2: 境界でバリデーション、内部では型を信頼する

```python
# ❌ 内部関数でもバリデーション
def _process_gap(entry: GapEntry) -> None:
    if entry is None:         # ← 呼び出し元がすでに保証している
        return
    if not entry.intent:      # ← 境界で済ませるべき
        return

# ✅ 境界（受信点）でのみバリデーション
class AvatarWSClient:
    def _on_message(self, raw: str) -> None:
        try:
            msg = AvatarMessage.parse(raw)   # ← ここで一度だけバリデーション
        except ValueError:
            return
        self._dispatch(msg)                  # ← 以降は型を信頼
```

C# 版:
```csharp
// ✅ Awake/受信点でガード、以後は null 非許容として扱う
void Awake() {
    _controller = GetComponent<AvatarController>();
    Debug.Assert(_controller != null, "AvatarController required");
}
```

**違反の影響**: バリデーションが散在し、エージェントがどこで検証されているか追跡できない。

---

## 原則 3: シークレットをコードに書かない（絶対禁止）

- APIキー・パスワード・OAuth トークンは `.env` / `config/` からのみ読む
- ハードコードされた URL・ポート番号は `config.py` / 設定ファイルに外出し
- ログ出力にパラメーター全体をダンプしない（センシティブなフィールドを除外）

```python
# ❌ ハードコード禁止
client = openai.OpenAI(api_key="sk-proj-...")

# ✅ 環境変数から読む
client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
```

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

**違反の影響**: ドキュメントが腐り、次のエージェントランで誤った判断をする。

---

## 原則 7: エラーメッセージは修正ヒントを含む

```csharp
// ❌ 情報不足
Debug.LogWarning("Policy not found");

// ✅ 次のアクションが明確
Debug.LogWarning($"[BehaviorPolicyLoader] intent='{intent}' not found in policy. " +
    $"Add an entry to StreamingAssets/behavior_policy.yml: '- intent: {intent}'");
```

```python
# ✅ どのファイルを直せばよいか示す
raise ValueError(
    f"Unknown safety level '{level}'. "
    f"Valid values: NG, GRAY, OK. See .github/srs/safety.yml"
)
```

---

## 違反検出（ガーベジコレクション）

以下のパターンを定期的に検索してリファクタリングする：

```python
# Python: 同一ロジックの重複を探す
# grep -r "def clamp\|min(.*, max(" AITuber/orchestrator/

# C#: Instance を直接参照せず GetComponent を使うべき場所
# grep -r "\.Instance\." AITuber/Assets/Scripts/Growth/
```

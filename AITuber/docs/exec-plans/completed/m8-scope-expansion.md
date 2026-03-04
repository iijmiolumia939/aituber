# M8 実行計画: 自律コード生成スコープ拡張 (Phase 2b)

> **作成**: 2026-03-04  
> **担当**: AI Agent  
> **依存**: M7 完了 (growth_loop.py / GrowthLoop)  
> **目標**: Phase-2b スコープ拡大 — `ScopeConfig` + `LLMModuloValidator` を実装し、
>   GrowthLoop が「YAMLのみ (2a)」に加えて「WS protocol 定義 (2b)」の提案を
>   スコープ制限付きで生成・検証できるようにする

---

## 問題と目標

### 現状 (M7 完了後)

```
GrowthLoop (growth_loop.py)
  └── ReflectionCLI → staging.yml → ApproveCLI → behavior_policy.yml
```

生成できる提案は `behavior_policy.yml` エントリ（Phase 2a）に固定されている。
また、LLM が生成した提案に対して「スコープ超過」「差分サイズ上限」を検査するゲートが存在しない。

### M8 ゴール

1. **`ScopeConfig`** — 現在の成長フェーズスコープを設定するクラス（2a〜2e）
2. **`LLMModuloValidator`** — 提案を `scope_gate` / `safety_gate` / `diff_size_gate` の 3 ゲートで検証
3. **`ProposalValidator` 拡張** — `proposal_type` フィールドに `ws_intent_definition` を追加
4. **`GrowthLoop` / `ReflectionCLI` に `scope_config` 選択肢を追加** — `--scope yaml_only|ws_protocol`
5. **`Assets/StreamingAssets/growth_scope.yml`** — ランタイムスコープ設定ファイル（デフォルト: yaml_only）

---

## 実装スコープ

### `orchestrator/scope_config.py` (新規)

```python
class GrowthScope(Enum):
    YAML_ONLY          = "yaml_only"           # Phase 2a: behavior_policy.yml のみ
    WS_PROTOCOL        = "ws_protocol"         # Phase 2b: WS intent 定義追加
    ANIMATOR           = "animator"            # Phase 2c: AnimatorController パラメーター
    ACTION_DISPATCHER  = "action_dispatcher"   # Phase 2d: ActionDispatcher.cs 新intent
    FULL_CS            = "full_cs"             # Phase 2e: 汎用C#スクリプト追加

@dataclass
class ScopeConfig:
    scope: GrowthScope = GrowthScope.YAML_ONLY
    max_proposals_per_run: int = 5
    max_diff_lines: int = 200
    # proposal_type 文字列ごとに許可スコープを定義
    # "behavior_policy_entry" は全スコープで常に許可
    # "ws_intent_definition" は WS_PROTOCOL 以上で許可

    @classmethod
    def from_yaml(cls, path: str) -> "ScopeConfig": ...
    def to_yaml(self, path: str) -> None: ...
    def allows_proposal_type(self, proposal_type: str) -> bool: ...
    def allowed_proposal_types(self) -> list[str]: ...
```

### `orchestrator/llm_modulo_validator.py` (新規)

```python
class GateStatus(Enum):
    PASS = "pass"
    FAIL = "fail"

@dataclass
class GateResult:
    gate_name: str
    status: GateStatus
    reason: str = ""

@dataclass
class LLMModuloReport:
    n_validated: int
    n_passed: int
    n_failed: int
    gate_results: list[GateResult]

class LLMModuloValidator:
    """3-gate validator for LLM-generated proposals.

    Gates:
      1. scope_gate     - proposal_type は ScopeConfig で許可されているか
      2. safety_gate    - ProposalValidator の安全チェックをパスするか
      3. diff_size_gate - 全提案の合計差分行数が max_diff_lines 以下か
    """
    def __init__(self, scope_config: ScopeConfig): ...
    def validate(self, proposals: list[dict]) -> tuple[list[dict], LLMModuloReport]: ...
    # 返り値: (通過した proposals のみ, 詳細レポート)
```

### `ProposalValidator` 拡張

- `proposal_type` フィールドを optional で追加（未指定時は `"behavior_policy_entry"` とみなす）
- `ws_intent_definition` 型の追加バリデーション:
  - 必須フィールド: `intent`, `ws_cmd`
  - `ws_cmd` allowlist: `avatar_intent`, `avatar_update`
  - `intent` は既存と同じ命名規則

### `growth_loop.py` / `reflection_cli.py` 拡張

- `GrowthLoop.__init__` に `scope_config: ScopeConfig | None = None` を追加
  - `None` の場合 `ScopeConfig()` (yaml_only) をデフォルト使用
  - `ReflectionCLI` 実行後・`ApproveCLI` 前に `LLMModuloValidator` でフィルタリング
- `build_parser()` に `--scope {yaml_only,ws_protocol}` フラグを追加

### `Assets/StreamingAssets/growth_scope.yml` (新規)

```yaml
# Growth scope configuration (Phase 2a default)
# SRS ref: autonomous-growth.md Phase 2
scope: yaml_only
max_proposals_per_run: 5
max_diff_lines: 200
```

---

## TDD テスト一覧

### `tests/test_scope_config.py`

| TC ID | クラス | 内容 |
|---|---|---|
| TC-M8-01 | `TestScopeConfigDefaults` | デフォルト: yaml_only, max 5, max 200 diff |
| TC-M8-02 | `TestScopeConfigYaml` | from_yaml / to_yaml ラウンドトリップ |
| TC-M8-03 | `TestScopeOrdering` | yaml_only < ws_protocol < animator ... |
| TC-M8-04 | `TestAllowedProposalTypes` | yaml_only → behavior_policy_entry のみ許可 |
| TC-M8-05 | `TestAllowedProposalTypes` | ws_protocol → behavior_policy_entry + ws_intent_definition 許可 |
| TC-M8-06 | `TestAllowsProposalType` | allows_proposal_type("unknown") → False |

### `tests/test_llm_modulo_validator.py`

| TC ID | クラス | 内容 |
|---|---|---|
| TC-M8-07 | `TestScopeGate` | behavior_policy_entry が yaml_only スコープで PASS |
| TC-M8-08 | `TestScopeGate` | ws_intent_definition が yaml_only スコープで FAIL |
| TC-M8-09 | `TestScopeGate` | ws_intent_definition が ws_protocol スコープで PASS |
| TC-M8-10 | `TestSafetyGate` | blocked word ("rm -rf") を含む提案が FAIL |
| TC-M8-11 | `TestDiffSizeGate` | n×proposals > max_diff_lines → FAIL |
| TC-M8-12 | `TestDiffSizeGate` | n×proposals <= max_diff_lines → PASS |
| TC-M8-13 | `TestMixed` | 有効1件 + 無効1件 → 通過1件、失敗1件のレポート |
| TC-M8-14 | `TestEmptyProposals` | 空リスト → report n_validated=0, n_passed=0 |
| TC-M8-15 | `TestReport` | LLMModuloReport フィールド等値比較 |

### `tests/test_proposal_validator_phase2b.py`

| TC ID | クラス | 内容 |
|---|---|---|
| TC-M8-16 | `TestWsIntentDefinition` | ws_intent_definition 型の valid 提案が VALID |
| TC-M8-17 | `TestWsIntentDefinition` | ws_cmd 欠損 → INVALID |
| TC-M8-18 | `TestWsIntentDefinition` | intent 欠損 → INVALID |
| TC-M8-19 | `TestWsIntentDefinition` | ws_cmd が allowlist 外 → INVALID |
| TC-M8-20 | `TestBehaviorPolicyBackcompat` | proposal_type 未指定でも既存バリデーション動作 |

### `tests/test_growth_loop_scope.py`

| TC ID | クラス | 内容 |
|---|---|---|
| TC-M8-21 | `TestScopeIntegration` | GrowthLoop に yaml_only ScopeConfig を渡すと ws_intent 提案がフィルタされる |
| TC-M8-22 | `TestScopeIntegration` | GrowthLoop に ws_protocol ScopeConfig を渡すと ws_intent 提案が通過する |
| TC-M8-23 | `TestParser` | `--scope yaml_only` / `--scope ws_protocol` フラグのパース |

---

## SRS 参照

- `FR-SCOPE-01` (新規): `ScopeConfig` により Growth Loop の生成スコープを外部設定できる
- `FR-SCOPE-02` (新規): `LLMModuloValidator` の 3 ゲートを全通過した提案のみ staging に進める
- `autonomous-growth.md` Phase 2b

---

## Done 判定

- [x] TC-M8-01〜23 全グリーン (50/50)
- [x] `ruff check` クリーン
- [x] `AGENTS.md` / `PLANS.md` / `QUALITY_SCORE.md` 更新済み
- [x] `autonomous-growth.md` M7/M8 完了マーク更新
- [x] `requirements.yml` に FR-SCOPE-01/02 追記
- [x] `aituber-tests.instructions.md` TC-M8-xx 追記
- [x] exec-plan `active → completed`
- [ ] `git commit && git push`

---

## 進捗ログ

| 日時 | 内容 |
|---|---|
| 2026-03-04 | exec-plan 作成 |
| 2026-03-04 | scope_config.py + llm_modulo_validator.py 実装完了, ProposalValidator Phase 2b 拡張, 50/50 グリーン, ruff クリーン, 全スイート 403 passed |

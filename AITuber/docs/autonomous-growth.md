# Autonomous Avatar Growth System

> **ステータス**: M1・M2・M3・M4・M5・M6・M7 実装完了（2026-03-03/04）— Phase 2a Growth Loop 全配線完了、M8 (Phase 2b) 実装中  
> **ゴール**: 配信を通してアバターが自律的に能力・表現・実装を成長させる  
> **評価**: 文献調査に基づき [アーキテクチャの根本的見直し](#設計評価と改訂方針) を実施済み（2026-03-03）

---

## 概要

アバターのAIは「今できること」の範囲内で視聴者とコミュニケーションを取るが、
**「やりたいことができなかった」という体験を積み重ね、自動的に実装・モーション・振る舞いを拡張していく**仕組みを構築する。

最終目標は **人間の介入なしに能力が広がり続けるアバター** の実現。

---

## 設計評価と改訂方針

文献調査（2026-03-03）に基づき、初期設計の適切性を多角的に評価した。

### 参照文献

| 論文 | 知見 | 本設計への示唆 |
|---|---|---|
| Park et al., 2023「Generative Agents」(arXiv:2304.03442) | **観察→計画→振り返り**のサイクルが信頼性の高いエージェント行動を生む。振り返りなしでは単なるリアクタに留まる | ReflectionループをPhase 1から必須化 |
| Zelikman et al., 2023「STOP」(arXiv:2310.02304) | LLMによる自己改善型コード生成は技術的に実現可能。ただし*スコープを限定しないとサンドボックス迂回が発生する* | Phase 2のコード生成スコープをYAML→WS protocol→C#の順に段階的に拡大 |
| Hong et al., 2023「MetaGPT」(arXiv:2308.00352) | LLMマルチエージェントでは**SOP（標準作業手順）**を事前定義しないとハルシネーションが連鎖する | GrowthAgentにSOP（仕様書生成→実装→テスト→安全チェック）を組み込む |
| Kambhampati et al., 2024「LLMs Can't Plan」(arXiv:2402.01817) | LLMは単体では自律的な計画検証ができない。**LLM-Modulo**（LLM生成 + 外部バリデーター）が必要 | Phase 2/3で全LLM出力に外部検証器を必須化 |
| South et al., 2025「Authenticated Delegation」(arXiv:2501.09674) | 自律エージェントには**認可スコープの明示的制限と監査ログ**が必要 | GrowthAgentが操作できるファイルパス・コマンドをホワイトリスト管理 |
| Huang et al., 2022「LLMs Can Self-Improve」(arXiv:2210.11610) | LLMは自己生成解からの学習で推論能力を向上できる。ただし*自信スコアによるフィルタリングが重要* | GapからのProposal生成には、LLMの確信度スコアによるフィルタを追加 |

### 初期設計の問題点（Critical）

#### 問題1: Intent層とAction層が分離されていない ⚠️

現在の `AvatarController` はWebSocket経由の**固定コマンド**（`gesture=nod`等）を受け取るだけ。「LLMが何をしたかったか（Intent）」と「実際に実行できたこと（Action）」の区別が存在しない。

```
現状（Gapが検出できない）:
LLM → "gesture=nod"コマント → AvatarController → 実行

あるべき姿:
LLM → Intent("point_at_screen") → ActionDispatcher → 実行可?
                                                        ├─ Yes → 実行
                                                        └─ No  → fallback="nod" + GapLog記録
```

GapLogの `intended_action` と `fallback_used` はこの分離なしに記録不可能。

#### 問題2: Reflection（振り返り）ループが設計に存在しない ⚠️

Generative Agents (Park et al., 2023) の核心は**「記憶→振り返り→計画の更新」サイクル**。
配信後にGapを集計するだけでは「何がなぜできなかったか」を抽象化できず、成長が発生しない。

#### 問題3: Phase 2のLLM出力を検証するバリデーターが未定義 ✅ 解決済み（M2）

~~LLMs Can't Plan (Kambhampati et al., 2024) によると、LLMは自己検証できない。
PRを自動生成しても「コンパイル通過」「テスト通過」「safety.yml準拠」を外部検証しないと人間のレビューコストが増大する。~~

**M2 で実装**: `ProposalValidator` が 5層チェック（スキーマ・cmd allowlist・intent命名・安全ワードブロック・重複）を適用。
`ReflectionRunner` は LLM-Modulo パターンを採用し、LLM 出力を必ずバリデーターに通す。

#### 問題4: Priority Scoreの算出が未具体化 ⚡

`(発生頻度) × (視聴者エンゲージメント係数) × (実装コスト逆数)` の「実装コスト」の自動見積もり手段が未定義。

### 設計改訂方針

1. **Intent/Actionモデルを追加** → WS protocol拡張で `intent` フィールドを独立させる
2. **Reflectionループを追加** → 配信後の振り返りをPhase 1から自動実行
3. **LLM-Modulo化** → ProposalGeneratorの出力には必ずコンパイル+テスト+安全検証ゲートを設ける
4. **スコープ制限の明確化** → Phase 2でAIが書けるものを「YAMLのみ」から段階的に拡大

---

## アーキテクチャ概念図（改訂版）

```
配信中 (Live Stream)
        │
        ▼
┌───────────────────────────────────────────────────────┐
│                Avatar State Machine                    │
│   State: idle / talking / reacting / thinking / ...   │
│                   ↓                                    │
│           [AI Brain (LLM)]                            │
│             ↓ Intent生成                              │
│     intent: { type="gesture", name="point_at_screen"} │
│                   ↓                                    │
│          [ActionDispatcher] ← BehaviorPolicy YAML     │
│           /               \                           │
│  Intent実行可能          Intent実行不可能              │
│       ↓                         ↓                     │
│   WS Command実行           fallback実行 + GapLog記録   │
└───────────────────────────────────────────────────────┘
                                  │
                ┌─────────────────┘
                ▼
      CapabilityGapLog (JSON)
                │
                ▼
┌───────────────────────────────────┐
│     Reflection Loop (配信後)       │  ← Phase 1から実装
│  GapLog集計 → 要約 → 振り返り文書   │
│  → GitHub Issue自動作成             │
│  → BehaviorPolicy更新候補生成       │
└───────────────────────────────────┘
                │
                ▼
         GrowthEngine (Phase別)
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
 Phase 1     Phase 2     Phase 3
人間が実装  AI提案→検証→PR  完全自律
```

### 重要な設計変更: Intent/Action分離

WS Protocolに `avatar_intent` コマンドを追加し、ActionDispatcher層を新設する。

```json
// 旧: AvatarControllerが直接受け取る固定コマンド
{ "cmd": "avatar_update", "params": { "gesture": "nod" } }

// 新: IntentをActionDispatcherが解釈して実行またはGapLog記録
{
  "cmd": "avatar_intent",
  "params": {
    "intent": "point_at_screen",
    "context": { "target": "comment_area" },
    "fallback": "nod"
  }
}
```

`ActionDispatcher` は `BehaviorPolicy` に登録されたintent→actionマッピングを検索し、
見つからない場合はfallbackを実行しつつ `GapLogger` に記録する。

---

## 状態とアクションのモデル

### アバターの状態 (State)

| State | 説明 | 代表的なアクション |
|---|---|---|
| `idle` | 配信開始・無音 | 環境を眺める、ちょっとした仕草 |
| `listening` | 視聴者コメント監視中 | 反応モーション、相槌 |
| `reading_comment` | コメント読み上げ中 | CommentAreaを向く、口の動き |
| `reacting` | 感情反応（驚き・笑い等） | 感情モーション、表情変化 |
| `thinking` | 回答生成中 | 考えポーズ、視線を下げる |
| `talking` | 音声再生中 | 口パク、ジェスチャー |
| `celebrating` | 配信マイルストーン | 特別モーション |
| `error` | 技術的問題発生 | リカバリ行動 |

### アクション種別

| カテゴリ | 具体例 | 現在の実装状況 |
|---|---|---|
| **視線制御** | camera/chat/commentArea向き | ✅ 実装済み |
| **表情** | happy/sad/surprised/angry/neutral | ✅ 実装済み |
| **ジェスチャー** | nod/shake/wave/point/think | 🔶 一部 |
| **ポーズ変化** | 立ち/座り/前傾き | ❌ 未実装 |
| **環境インタラクション** | 小道具を触る/背景オブジェクト操作 | ❌ 未実装 |
| **視聴者への直接反応** | 名前呼び/スーパーチャット反応 | ❌ 未実装 |
| **自発的会話開始** | アイドル時に独り言 | ❌ 未実装 |

---

## Capability Gap Log

「やりたいができなかった」を記録する中核コンポーネント。

### ログエントリ構造

```json
{
  "timestamp": "2026-03-03T12:34:56Z",
  "stream_id": "stream_20260303",
  "trigger": "viewer_comment",        // きっかけ
  "current_state": "reacting",
  "intended_action": {
    "type": "gesture",
    "name": "point_at_screen",        // やりたかったこと
    "params": { "target": "comment" }
  },
  "fallback_used": "nod",            // 代わりに実行したこと
  "context": {
    "comment_text": "画面を指差して！",
    "emotion": "happy",
    "viewer_id": "xxx"
  },
  "gap_category": "missing_motion",  // gap種別
  "priority_score": 0.0              // GrowthEngineが自動算出
}
```

### Gap カテゴリ一覧

| カテゴリ | 意味 | 解決手段 |
|---|---|---|
| `missing_motion` | モーション/アニメーションが存在しない | モーション追加 |
| `missing_expression` | 表情ブレンドシェイプが不足 | VRMセットアップ更新 |
| `missing_behavior` | 状態遷移ルールが未定義 | BehaviorPolicyを拡張 |
| `missing_integration` | 外部サービス未連携（BGM等） | 新機能実装 |
| `capability_limit` | LLMが意図を持てるが実行APIがない | WS protocol拡張 |
| `environment_limit` | 部屋・小道具が存在しない | アセット追加 |

---

## 成長エンジン (GrowthEngine) フェーズ計画

### Phase 1 — 観測・手動実装 + Reflection（現在）

**目的**: Gapを可視化して人間が優先順位をつけて実装する。Reflectionループをこの段階から稼働させる。

```
配信中:
  ActionDispatcher → GapLogger → Logs/capability_gaps/<stream_id>.jsonl

配信終了後（自動）:
  ReflectionRunner (Python)
    ├── GapLog集計・クラスタリング
    ├── LLMで「今配信のGap要約文」生成
    ├── GitHub Issue自動作成（タイトル=上位Gap）
    └── BehaviorPolicyの更新候補YAMLを draft として保存

人間:
  Issueをレビュー → Gitブランチで実装 → マージ
```

**実装物**:
- `ActionDispatcher` (C#): Intent→Action変換 + Gap検出
- `GapLogger` (C#): Gap発生時にJSONLを書き出す（`Logs/capability_gaps/`）
- `GapDashboard` (Python/CLI): ログを集計・可視化
- `ReflectionRunner` (Python): 配信後に自動実行するReflectionスクリプト
- priority_score算出:
  ```
  score = (発生頻度_7日) × (engagementΔ: コメント増減率) × (1 / estimated_lines)
  estimated_lines: gap_categoryごとの中央値（YAML=5行, WS=10行, motion=50行, C#=100行）
  ```

### Phase 2 — AI提案・LLM-Modulo検証・人間承認（中期目標）

**目的**: AIがGapに対する実装案を自動生成し、外部検証をパスしたPRを人間が承認するだけにする。

```
ReflectionRunner出力 (上位Gap + 振り返り要約)
    ↓
ProposalGenerator (LLM + SOP)
    ├── Step1: gap_categoryに応じたノルール確認 (SRS.md参照)
    ├── Step2: 実装案生成 (スコープ制限付き)
    └── Step3: テストケース案生成
    ↓
LLM-Modulo Validator (外部検証器)   ← LLMs Can't Plan の知見
    ├── コンパイルゲート (dotnet build)
    ├── テストゲート (Unity Test Runner)
    ├── safety.yml準拠チェック
    └── 変更スコープ上限チェック（diffサイズ）
    ↓
全ゲート通過 → GitHub PR自動作成
    ↓
人間がPRをレビュー・承認 → CI/CD でビルド・デプロイ
```

**コード生成スコープ（段階的拡大）**:
| Phase 2サブフェーズ | 生成できるもの |
|---|---|
| 2a (開始時) | `behavior_policy.yml` エントリのみ |
| 2b | WS protocol定義の追加 |
| 2c | AnimatorControllerパラメーター追加 |
| 2d | `ActionDispatcher.cs` の新intent追加 |
| 2e | 汎用C#スクリプト追加（新ファイルのみ） |

**実装物**:
- `ProposalGenerator` (Python): SOPに従ってLLMにProposalを生成させるスクリプト
- `LLMModuloValidator` (Python): 各ゲートをパイプラインで実行する検証器
- CI/CD workflow (GitHub Actions): PR作成 → 自動ビルド・テスト整備

### Phase 3 — 完全自律実装（長期目標）

**目的**: 人間の介入なしにアバターが次回配信前に能力を拡張する。

```
ReflectionRunner (毎配信後・自動)
    ↓
GrowthAgent (SOP準拠マルチエージェント)
    ├── AnalystAgent: Gap優先順位決定
    ├── ArchitectAgent: 実装設計（スコープ内）
    ├── CoderAgent: コード/YAML生成
    ├── TestAgent: テスト生成・実行
    └── SafetyAgent: guardrails最終確認
    ↓
LLM-Modulo Validator (全ゲート)
    ↓
全ゲート通過 → ステージング環境でPlayMode動作確認
    ↓
自動デプロイ (次回配信前)
```

**技術課題と対処方針**:

| 課題 | 対処方針 |
|---|---|
| Unity C#のドメインリロード | スクリプト変更後はUnityを`-batchmode -quit`で再ビルド、次回起動時に反映 |
| モーション自動生成 | Phase 3aは手続き的生成（ボーン角度仕様書→AnimationClip生成スクリプト）、Phase 3bでMLMotion検討 |
| 回帰テスト | 配信ごとに「正常動作録画」をキャプチャして次回ビルドと比較するGoldenTest導入 |
| LLMハルシネーション | MetaGPTのSOP方式を採用。各AgentはSRSの対応FRIDを必ず引用 |

---

## Reflection Loop

Generative Agents (Park et al., 2023) の知見に基づき、**観察→振り返り→計画更新**を毎配信後に実行する。

```
配信終了
    ↓
[1. 観察] GapLog集計
  - 総Gap件数・カテゴリ別集計
  - 視聴者エンゲージメント時系列との相関

[2. 振り返り] ReflectionRunner (LLM)
  プロンプト:
  「今日の配信でアバターは以下のGapを経験した: <gap_summary>
   視聴者の反応が最も高かった瞬間は: <engagement_peak>
   何が不足していたか・次回どう改善するかを100字で要約せよ」

[3. 計画更新]
  - behavior_policy.yml の draft更新候補を生成
  - GitHub Issueとして振り返りテキストを投稿
  - priority_scoreを再算出してGrowthEngineに返す
```

**Reflectionの出力例**:
```json
{
  "stream_id": "stream_20260303",
  "reflection": "視聴者から指差し要求が3回あったが全てnodでfallbackした。gestures配下のpoint_at系モーションが最優先の欠損。次回配信前にgesture_point_forwardを実装することで推定エンゲージメント+12%が期待できる。",
  "top_gap": "gesture_point_forward",
  "policy_draft": [
    {
      "intent": "point_at_screen",
      "action": "gesture_point_forward",
      "notes": "要実装 - gestures配下"
    }
  ]
}
```

---

## BehaviorPolicy — 状態×文脈 → アクション写像

アバターの「どの状態でなにをするか」を外部データとして管理し、学習で更新できるようにする。

```yaml
# behavior_policy.yml (例)
- state: listening
  trigger: viewer_count_milestone
  threshold: 100
  action:
    type: celebrate
    motion: wave_both_hands
    expression: happy
    voice_line: "100人ありがとうございます！"
  priority: high

- state: reading_comment
  trigger: comment_contains_question
  action:
    type: gaze
    target: comment_area
    then: think_pose
  priority: normal
```

- このYAMLはGitで管理し、配信経験から得たデータを元に自動更新 (Phase 3)
- `BehaviorPolicyLoader` (C#) が起動時にロードし、`AvatarController` に渡す

---

## モーション拡張プロセス

```
Gap: missing_motion "point_at_screen"
    ↓
仕様書自動生成（対象ボーン・角度範囲・秒数・ループ有無）
    ↓
[Phase 1] 人間がUnity Animationで手作成
[Phase 3] ML/手続き的生成 → Animation Clipを自動生成
    ↓
命名規則に従い AnimatorController に登録
    ↓
WS Protocol の action.name に追加
    ↓
GapLogの該当エントリをクローズ
```

**モーション命名規則**:

```
<カテゴリ>_<動作>_<バリアント>
例: gesture_point_forward, gesture_wave_right, emote_laugh_big
```

---

## 技術スタック（成長システム）

| コンポーネント | 技術 | 配置 | フェーズ |
|---|---|---|---|
| ActionDispatcher | C# (Unity) | `Assets/Scripts/Growth/ActionDispatcher.cs` | Phase 1 ✅ M1 |
| GapLogger | C# (Unity) | `Assets/Scripts/Growth/GapLogger.cs` | Phase 1 ✅ M1 |
| GapDashboard | Python (click + rich) | `orchestrator/gap_dashboard.py` | Phase 1 ✅ M3 |
| ReflectionRunner | Python (LLM client) | `orchestrator/reflection_runner.py` | Phase 1 ✅ M2 |
| ProposalValidator | Python | `orchestrator/proposal_validator.py` | Phase 1 ✅ M2 |
| PolicyUpdater | Python | `orchestrator/policy_updater.py` | Phase 1 ✅ M2 |
| BehaviorPolicy | YAML + C# loader | `Assets/StreamingAssets/behavior_policy.yml` | Phase 1 ✅ M1 |
| GrowthLoop | Python | `orchestrator/growth_loop.py` | Phase 1 ✅ M7 |
| ScopeConfig | Python | `orchestrator/scope_config.py` | Phase 2 🔧 M8 |
| LLMModuloValidator | Python | `orchestrator/llm_modulo_validator.py` | Phase 2 🔧 M8 |
| ProposalGenerator | Python (LLM + SOP) | `tools/growth/proposal_generator.py` | Phase 2 |
| GrowthAgent | Python (マルチエージェント) | `tools/growth/growth_agent.py` | Phase 3 |
| CI/CD | GitHub Actions | `.github/workflows/growth-*.yml` | Phase 2〜 |

---

## セーフガード（改訂版）

初期設計に South et al. (2025) のAuthorized Delegation知見を反映。

| # | ガード | 説明 | フェーズ |
|---|---|---|---|
| G1 | **safety.yml ゲート** | 全ルールをパスしないと自動デプロイ不可 | 全フェーズ |
| G2 | **bandit.yml 準拠** | コンテンツポリシーを LLMModuloValidator が自動検証 | Phase 2〜 |
| G3 | **変更スコープ上限** | 1回の自動更新: ファイル≤5・diff≤200行 | Phase 2〜 |
| G4 | **ホワイトリスト** | GrowthAgentが書き込めるパスを明示的に制限（`StreamingAssets/`・`Assets/Scripts/Growth/`・`Animations/Generated/`のみ） | Phase 3 |
| G5 | **ロールバック** | 配信開始後5分以内にエラー率が閾値超過 → 自動ロールバック | Phase 2〜 |
| G6 | **人間承認ゲート** | Phase 2まではPR承認必須。Phase 3移行は明示的フラグ切り替え要 | Phase 1〜2 |
| G7 | **Reflection要約の人間読み** | 毎配信後のIssue通知は必ず人間がチェックする（自動closeしない） | 全フェーズ |

---

## マイルストーン（改訂版）

| Milestone | 内容 | 依存 | 目安 |
|---|---|---|---|
| M1 | `ActionDispatcher` + `GapLogger` 実装・ログ収集開始（[設計書](m1-design.md)） | — | ✅ 2026-03-03 (61/61 TC) |
| M2 | `ReflectionRunner` + `ProposalValidator` + `PolicyUpdater` 実装（[完了記録](exec-plans/completed/m2-reflection-runner.md)） | M1 | ✅ 2026-03-03 (41/41 TC) |
| M3 | `GapDashboard` で初回集計・上位5 Gap特定・Issue作成 | M2 | ✅ 2026-03-03 (26/26 TC) |
| M4 | 上位GapのモーションをPhase 1で手動実装（初回成長） | M3 | ✅ 2026-03-04 (24/24 TC) |
| M5 | `reflection_cli.py` で `OpenAIBackend` を注入し Growth Loop を end-to-end で配線。TD-010 解消 ([完了記録](exec-plans/completed/m5-reflection-cli.md)) | M4 | ✅ 2026-03-04 (11/11 TC) |
| M6 | `approve_cli.py` で人間承認フロー実装。`reflection_cli --output` staging + 対話 y/n + `--auto-approve` (CI)。Phase 2 Growth Loop 全配線 ([完了記録](exec-plans/completed/m6-approve-cli.md)) | M5 | ✅ 2026-03-04 (14/14 TC) |
| M6 | `approve_cli.py` で人間承認フロー実装。`reflection_cli --output` staging + 対話 y/n + `--auto-approve` (CI)。Phase 2 Growth Loop 全配線 ([完了記録](exec-plans/completed/m6-approve-cli.md)) | M5 | ✅ 2026-03-04 (14/14 TC) |
| M7 | `growth_loop.py` で Phase-2 ループを 1 コマンドで実行。`GrowthLoop` + `GrowthLoopResult`。FR-LOOP-01/02 ([完了記録](exec-plans/completed/m7-growth-loop.md)) | M6 | ✅ 2026-03-04 (13/13 TC) |
| M8 | `ScopeConfig` + `LLMModuloValidator` + Phase 2b WS protocol スコープ拡大。FR-SCOPE-01/02 ([exec-plan](exec-plans/active/m8-scope-expansion.md)) | M7 | 🔧 2026-03-04 実装中 |
| M9 | 完全自律デプロイ実験（Phase 3パイロット） | M8 | TBD |

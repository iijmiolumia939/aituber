# Autonomous Avatar Growth System

> **ステータス**: M1〜M20 全実装完了（2026-03-03＞05）— Phase 2b・日常生活 Sims-like 行動シーケンス・行動完全統合まで完了  
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

#### 身体運動・自立行動に関する追加文献（2026-03-06 追記）

| 論文 | 知見 | 本設計への示唆 |
|---|---|---|
| Rao & Georgeff, 1991「BDI: Modeling Rational Agents」IJCAI Proceedings | **Beliefs（世界モデル）→ Desires（目標）→ Intentions（実行）** の三層。世界知覚なしで意図を生成すると非整合行動が生まれる | `WorldContext`（現在ゾーン・ポーズ）を `LifeScheduler.tick(current_zone=…)` に入力し、既にターゲットゾーンにいる場合の冗長 `walk_to` を排除（Issue #46） |
| Ahn et al., 2022「SayCan: Do As I Can, Not As I Say」(arXiv:2204.01691) | LLMが意図を生成しても、**現在の身体・環境で実行可能か（Affordance）の事前確認**が必須。「言えること ≠ できること」という Grounding 問題 | `BehaviorSequenceRunner` が `walk_to` 前に NavMesh 経路を確認し、取れなければ `gap_category: locomotion_blocked` としてGapLogに記録（Issue #44 拡張） |
| Puig et al., 2018「VirtualHome: Simulating Household Activities」(arXiv:1806.07011) | 室内生活アクティビティを **原子アクション（walk_to / sit / lie / pick_up）の連鎖**で表現し Unity3D上で実行。アトム化することでロバスト性と拡張性が上がる | `behaviors.json` のステップモデル（`walk_to→gesture→wait`）の理論的土台。現行は `walk_to` が 1ステップで位置遷移を完結しているが、**向き合わせ・速度ランプ・到達確認**の細分化が品質向上の鍵 |
| Wang et al., 2023「A Survey on LLM-based Autonomous Agents」(arXiv:2308.11432) | **Perception-Memory-Action ループの閉包**が自律エージェントの安定性に不可欠。行動の完了/失敗が記憶に還流しないと成長しない | `BehaviorSequenceRunner` の完了・失敗を `perception_update` で Python に返送し GapLog へフィード（Issue #44） |

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

#### 問題5: 身体運動（Locomotion）品質が自立行動の believability を損なう ⚠️

文献調査（BDI / SayCan / VirtualHome）に基づき、現行 `BehaviorSequenceRunner` の locomotion 品質に以下の欠陥が確認された。

| # | 欠陥 | 対応文献 | 影響 |
|---|---|---|---|
| L-1 | `walk_to` 前に NavMesh 経路を確認しない → 壁抜け・ワープが発生 | SayCan (Affordance) | アバターが壁を突き抜けて視聴者に不自然な印象 |
| L-2 | 歩行開始時にアバターが目的地を向かずスライドする（ターン先行なし） | VirtualHome (原子分解) | 人間的な動きに見えない |
| L-3 | walk→停止→ジェスチャーが 1 フレームでスイッチ（Blend Tree なし） | VirtualHome (アトム細分化) | アニメーション遷移がぎこちない |
| L-4 | `WorldContext`（現在ゾーン）が `LifeScheduler` に入力されない | BDI (Beliefs→Desires) | 既に desk にいるのに `go_stream` を再送する冗長移動 |
| L-5 | `BehaviorSequenceRunner` の完了/失敗が Python 側に通知されない | Survey (Perception-Memory-Action) | GapLog に locomotion 失敗が記録されず Growth が学習できない |

**現行利用可能 Asset の調査**（`Assets/Scripts/` 調査済み）:

| Asset | 現状 | Locomotion品質への活用度 |
|---|---|---|
| `BehaviorSequenceRunner.cs` | NavMeshAgent + CharacterController で `walk_to` 実行 | ✅ 基盤あり。L-1〜L-3 の改善が必要 |
| `AvatarGrounding.cs` | CharacterController 重力・着地 + Foot IK（`_enableFootIK = false` で無効） | ⚡ Foot IK は実装済みだが **無効化されたまま**。歩行中の足ズレ補正に活用可能 |
| `AvatarIKProxy.cs` | Animator → AvatarGrounding への IK コールバック転送 | ✅ 有効。Foot IK 有効化時に自動機能 |
| `InteractionSlot.cs` | ルーム内の名前付きスロット（`sit_work`, `sleep_area`, `sofa`） | ✅ walk_to のターゲット座標・向き定義の基盤 |
| `NavMeshAgent` (UnityEngine.AI) | `BehaviorSequenceRunner` が `_navMeshAgent` として参照 | ✅ 経路確認 API（`CalculatePath`）が利用可能 → L-1 修正の根拠 |
| `AvatarAnimatorController.controller` | Animator に 20+ クリップ。Blend Tree **なし**。Walk state `m_WriteDefaultValues=0` | ❌ Blend Tree 未整備がアニメーション品質の主要ボトルネック |
| `behaviors.json` | `walk_to→gesture→wait` の 3 ステップモデル | ⚡ VirtualHome 教訓に基づく細分化（`face_toward` ステップ追加）が必要 |

**修正ロードマップ（L-1〜L-5 対応）**:

```
L-1: BehaviorSequenceRunner.walk_to前に NavMesh.CalculatePath() でAffordance確認
     → 経路なし → gap_category: locomotion_blocked をGapLogに記録

L-2: behaviors.json に face_toward ステップ型を追加
     { "type": "face_toward", "slot_id": "sit_work", "duration": 0.4 }
     → walk_to 前にアバターを目的地に向かせる

L-3: AvatarAnimatorController に Blend Tree 追加
     speed パラメーター → Idle(0) ⇔ Walk(1) を補間
     + Walk state m_WriteDefaultValues: 1 に修正

L-4: LifeScheduler.tick(current_zone=WorldContext.current_zone) に変更
     (Issue #46)

L-5: BehaviorSequenceRunner がシーケンス完了時に
     perception_update { "behavior_completed": "go_stream", "success": true } を送信
     → Python _on_perception_update → GapLogger.RecordCompletion()
```

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
| **ジェスチャー** | nod/shake/wave/point/think | ✅ 実装済み (20クリップ) |
| **ポーズ変化** | 立ち/座り/前傾き/睡眠/歩行 | ✅ M4+M19 で実装 |
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
| `missing_expression` | 表情ブレンドシェイプが不足 | BlendShapeインデックス更新 |
| `missing_behavior` | 状態遷移ルールが未定義 | BehaviorPolicyを拡張 |
| `missing_integration` | 外部サービス未連携（BGM等） | 新機能実装 |
| `capability_limit` | LLMが意図を持てるが実行APIがない | WS protocol拡張 |
| `environment_limit` | 部屋・小道具が存在しない | アセット追加 |
| `locomotion_blocked` | NavMesh経路が取れず walk_to が実行不可（SayCan: Affordance 失敗） | InteractionSlot 位置修正 / NavMesh Bake 再設定 |
| `locomotion_quality` | 経路は取れるが遷移品質が低い（ターンなし・Blend Treeなし等） | L-1〜L-3 ロードマップ適用 |
| `world_belief_stale` | WorldContext が更新されず古い状態で行動選択された（BDI: Beliefs失効） | perception_update サイクル短縮 / Issue #46 修正 |

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

## Runtime Memory Layers (2026-03-14)

人間らしい継続性を配信ランタイムで出すため、Growth System の Reflection と runtime recall を分離する。

| Layer | 役割 | 実装状況 |
|---|---|---|
| Episodic Memory | 会話・行動結果・失敗/成功イベントの痕跡を保存し、現在文脈で想起する | ✅ M26 完了 (`episodic_store.py`) |
| Semantic Memory | 視聴者との関係性や反復トピックなど、耐久性のある facts を圧縮保持する | ✅ M27 完了 (`semantic_memory.py`) |
| Narrative Memory | 自己物語として現在の自己像を形成し、semantic/goal continuity を idle talk に還流する | ✅ M28 完了 (`narrative_builder.py`) |
| Goal Memory | 中期的な約束・継続課題・関心を管理し、LifeScheduler に bias を与える | ✅ M28 完了 (`goal_memory.py`) |
| Maintenance Layer | persisted runtime memory を配信後に整形し、archive / promotion を行う | ✅ M29 完了 (`memory_maintenance_cli.py`) |

M26 では `EpisodeEntry` に runtime metadata を追加し、importance だけでなく freshness・access_count・viewer continuity・time bucket・scene continuity・room continuity・nearby object continuity を使って想起順位を決めるようにした。これにより、同じ視聴者への継続応答や行動結果の記憶が会話に反映されやすくなる。

M27 では transcript をそのまま持ち続けるのではなく、viewer familiarity と repeated topic interest を durable facts として抽出する。これにより、prompt に大きな transcript を再注入せずに「この人は常連」「この人は shader の話題を継続的にしている」といった性質を保てる。

M28 の第一段では `goal_memory.py` を追加し、会話で繰り返される topic を medium-horizon goal として保持する。reply path では `[GOALS]` block を `[WORLD]` / `[FACTS]` / `[MEMORY]` に加えて注入し、`NarrativeBuilder` は semantic overview と goal fragment を含めて自己物語を生成する。`LifeScheduler` は短期の `GoalState` を維持したまま、goal focus type に応じて READ/TINKER/PONDER などへ軽い bias を加える。

さらに `behavior_completed` の成功 / 失敗イベントも `GoalMemory` に取り込み、`go_stream` のような成功は social continuity、`locomotion_blocked` のような失敗は exploration / maintenance continuity に変換する。これにより、会話だけでなく自律行動の結果も「今は何を深めるべきか」に反映される。

加えて、`続き` を含む会話は `follow_up_goal` として扱い、topic の継続スレッド自体を goal continuity に昇格させる。idle talk では goal / life / narrative の各 hint を無制限に積まず、現在性の高い hint を最大 2 件まで選別して prompt の肥大化を防ぐ。

この `follow_up_goal` には viewer 単位の subject を持たせ、reply prompt では同じ視聴者に紐づく continuation thread を優先する。ナラティブ生成でも goal line を 1 本だけでなく上位 2 本まで参照し、現在の自己像が単一テーマに固定されすぎないようにしている。

さらに viewer familiarity も goal priority に取り込み、`regular` / `superchatter` 相当の視聴者では continuation thread の優先度を一段強くする。narrative loop では top goals を query 化して episodic recall を行い、直近会話と goal-relevant memory を混ぜた材料から自己物語を組み立てる。

ここに goal subject を continuity signal として加え、特定視聴者との継続スレッドがある場合は narrative recall でもその viewer を優先できるようにした。加えて `time_bucket`・`scene_name`・`room_name`・`objects_nearby` も episodic recall に渡し、朝の home/desk で monitor が見えていた場面の記憶は、同じ scene/room/時間帯/周辺物を持つ現在文脈で優先しやすくしている。また reply prompt では semantic facts と goals の topic 重複を軽く削減し、viewer relationship のような情報を残したまま文脈ブロックの冗長さを抑えている。

直近の refinement では、この分離を post-hoc dedupe だけに依存させず、`SemanticMemory.to_prompt_fragment()` / `to_overview_fragment()` に `exclude_topics` を導入した。これにより、active goal と衝突する topic は `[FACTS]` の生成段階で除外され、semantic layer は「誰との関係か」「どんな背景関心があるか」、goal layer は「今どの継続 thread を拾うか」という役割に寄せている。

M29 では runtime path に hook を増やさず、persisted JSONL に対する post-stream maintenance を `memory_maintenance_cli.py` として分離した。maintenance は dry-run で merge/archive/promotion の件数を inspect でき、apply 時には duplicate episode burst を統合し、古くて low-signal な non-conversation / non-viewer episode を archive に退避する。さらに archived episode からは、未登録の viewer profile / viewer interest / topic goal だけを保守的に backfill することで、prompt path の current weighting を壊さずに long-tail context を durable layer へ圧縮する。
この apply 書き込みは active episodic store を最後に atomic replace する順序にし、archive や durable memory の保存失敗で唯一の episode copy を失わないようにしている。

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
| ScopeConfig | Python | `orchestrator/scope_config.py` | Phase 2 ✅ M8 |
| LLMModuloValidator | Python | `orchestrator/llm_modulo_validator.py` | Phase 2 ✅ M8 |
| WsSchemaValidator | Python | `orchestrator/ws_schema_validator.py` | Phase 2 ✅ M9 |
| BehaviorDefinitionLoader | C# (Unity) | `Assets/Scripts/Behavior/BehaviorDefinitionLoader.cs` | Phase 2 ✅ M19 |
| BehaviorSequenceRunner | C# (Unity) | `Assets/Scripts/Behavior/BehaviorSequenceRunner.cs` | Phase 2 ✅ M19 |
| BehaviorSequences (data) | JSON | `Assets/StreamingAssets/behaviors.json` | Phase 2 ✅ M19 |
| AvatarGrounding (Foot IK) | C# (Unity) | `Assets/Scripts/Avatar/AvatarGrounding.cs` | Phase 2 ⚡ `_enableFootIK` 有効化待ち |
| face_toward ステップ対応 | C# (Unity) | `BehaviorSequenceRunner.cs` 拡張 | Phase 2 ❌ 未実装 (L-2) |
| NavMesh Affordance 確認 | C# (Unity) | `BehaviorSequenceRunner.cs` 拡張 | Phase 2 ❌ 未実装 (L-1) |
| BSR completion callback | C# + Python | `BehaviorSequenceRunner` → `perception_update` | Phase 2 ❌ 未実装 (L-5) |
| Blend Tree (walk speed) | AnimatorController | `AvatarAnimatorController.controller` | Phase 2 ❌ 未実装 (L-3) |
| ProposalGenerator | Python (LLM + SOP) | `tools/growth/proposal_generator.py` | Phase 3 |
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
| M7 | `growth_loop.py` で Phase-2 ループを 1 コマンドで実行。`GrowthLoop` + `GrowthLoopResult`。FR-LOOP-01/02 ([完了記録](exec-plans/completed/m7-growth-loop.md)) | M6 | ✅ 2026-03-04 (13/13 TC) |
| M8 | `ScopeConfig` + `LLMModuloValidator` + Phase 2b WS protocol スコープ拡大。FR-SCOPE-01/02 | M7 | ✅ 2026-03-04 (50/50 TC) |
| M9 | WebSocket スキーマバリデーション。`WsSchemaValidator`。FR-WS-SCHEMA-01/02 | M8 | ✅ 2026-03-04 (41/41 TC) |
| M10 | TTS/AudioPlayer テスト強化。`extract_visemes` + `VoicevoxBackend` mock。FR-LIPSYNC-01/02 | M9 | ✅ 2026-03-04 (23/23 TC) |
| M11 | Bandit ε自動調整。`adapt_epsilon` + `auto_adapt`。FR-BANDIT-EPS-01 | M10 | ✅ 2026-03-04 (14/14 TC) |
| M12 | Room/Environment テスト強化。TC-ROOM-01〜18 (Unity EditMode) | M11 | ✅ 2026-03-04 (18/18 TC) |
| M13 | CI Unity ビルド自動化。`.github/workflows/ci.yml` + `unity-ci.yml` (game-ci/unity-test-runner@v4) | M12 | ✅ 2026-03-04 |
| M14 | Overlay 自動テスト。`overlay_server.py` バグ修正。TC-OVL-01〜20 | M13 | ✅ 2026-03-04 (20/20 TC) |
| M15 | LLM バックエンド切替。`LLM_BASE_URL`/`LLM_MODEL` 環境変数。FR-LLM-BACKEND-01 | M14 | ✅ 2026-03-04 (6/6 TC) |
| M16 | `LIVE_CHAT_ID` 自動取得。`fetch_active_live_chat_id`。FR-CHATID-AUTO-01 | M15 | ✅ 2026-03-04 (9/9 TC) |
| M17 | YUI.A 世界観ブラッシュアップ。`behavior_policy` +6 intents。FR-YUIA-INT-01〜06 | M16 | ✅ 2026-03-04 (21/21 TC) |
| M18 | 配信前 Inspector/設定確認。BlendShape全設定(26項目)・TTS・VRM・Animator・Room確認 | M17 | ✅ 2026-03-04 |
| M19 | 日常生活 Sims-like 行動シーケンス。`BehaviorSequenceRunner` + `behaviors.json`。FR-LIFE-01, FR-BEHAVIOR-SEQ-01 | M18 | ✅ 2026-03-05 |
| M20 | `behavior_start` cmd 統合。`BehaviorDefinitionLoader`・`BehaviorStartParams`・ActionDispatcher 配線。`behavior_policy` M19 intents を behavior_start に移行。`RoomManager.TryGetZone` 追加。FR-BEHAVIOR-SEQ-01 | M19 | ✅ 2026-03-05 |
| M26 | Episodic Recall Engine。`episodic_store.py` に metadata-aware recall と behavior completion ingestion を導入 | M20 | ✅ 2026-03-14 |
| M27 | Semantic Memory Layer。viewer familiarity と repeated topic facts を runtime durable memory として追加 | M26 | ✅ 2026-03-14 |
| M28 | Narrative and Goal Continuity。goal memory、viewer-aware follow-up、ambient grounded recall を導入 | M27 | ✅ 2026-03-14 |
| M29 | Runtime Memory Maintenance。post-stream CLI に duplicate merge / stale archive / conservative promotion を導入 | M28 | ✅ 2026-03-14 |
| M21 | 完全自律デプロイ実験（Phase 3パイロット） | M20 | TBD |

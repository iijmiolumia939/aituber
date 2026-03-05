#!/usr/bin/env python3
"""
Create GitHub Issues for "Embodied AI in Unity World" concept.

Background: AITuber のコンセプトは「Unity 世界に体を持つ AI」として
人間キャラクターと対話する仮想存在。
以下の研究領域を参考に機能 Issue を作成する。

参考文献:
- Agent AI (Durante et al., 2024) arXiv:2401.03568
  "a class of interactive systems that can perceive visual stimuli, language
   inputs, and other environmentally-grounded data"
- Generative Agents (Park et al., 2023) arXiv:2304.03442
  memory stream / reflection / planning for believable behavior in virtual worlds
- CoALA (Sumers et al., 2023) arXiv:2309.02427
  Cognitive Architectures: episodic memory, semantic memory, action space
- SimToM (Wilf et al., 2023) arXiv:2311.10227
  Theory of Mind: perspective-taking, mental state inference
"""

import json
import urllib.request

REPO   = "iijmiolumia939/aituber"
TOKEN  = "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"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
}

# ─── ラベル定義 ─────────────────────────────────────────────────────────────────

NEW_LABELS = [
    {"name": "embodied-ai",  "color": "5319e7", "description": "Embodied AI / situated agent"},
    {"name": "world-model",  "color": "0075ca", "description": "Unity world state perception"},
    {"name": "memory",       "color": "e4e669", "description": "Episodic / semantic memory"},
    {"name": "persona",      "color": "d93f0b", "description": "Persona consistency / identity"},
    {"name": "theory-of-mind","color": "0e8a16","description": "Theory of Mind / perspective-taking"},
]

# ─── Issue 定義 ──────────────────────────────────────────────────────────────────

ISSUES = [
    {
        "title": "[Embodied AI] E-1: Unity 世界の住人としての自己認識 (Situatedness)",
        "labels": ["embodied-ai", "persona", "P1-important"],
        "body": """\
## 概要

アバターが「自分は Unity の仮想世界に実在する存在だ」という自己認識 (**Situatedness / World-Grounding**) を持つように、
システムプロンプト・行動方針・会話層を整備する。

## 背景・文献

> "Agent AI: a class of interactive systems that can perceive visual stimuli,
> language inputs, and **other environmentally-grounded data**, and can produce
> meaningful **embodied actions**."
> — Durante et al. (2024), Agent AI, arXiv:2401.03568

現在の YUI.A は観察者・観測者という内面を持っているが、
「自分がいる空間 (部屋/ステージ)」「自分の体を持っていること」への言及が薄い。

## やること

- [ ] `yuia.yml` system_prompt に世界観セクション追記
  - 「私はデジタル世界に体を持つ AI だ」という一人称記述
  - 現在いる Room (錬金術師の部屋) を自己紹介文脈に組み込む
- [ ] behavior_policy に `situated_response` インテント追加
  - コメントで「どこにいるの？」「体はあるの？」等を受けた際の応答パターン
- [ ] `orchestrator/world_context.py` を新規作成
  - Unity から `scene_name` / `room_name` を受け取り system_prompt に注入できる設計

## 受け入れ条件

- [ ] YUI.A が「私は〇〇の部屋にいます」と答えられる
- [ ] system_prompt に `[WORLD]` セクションが存在する
- [ ] テスト: `test_world_context.py` TC-WORLD-01〜05 グリーン

## 参考

- arXiv:2401.03568 §3 "Grounded Agent AI"
- AGENTS.md M17 (YUI.A 世界観ブラッシュアップ)
""",
    },
    {
        "title": "[Embodied AI] E-2: エピソード記憶 — 会話・イベントの長期保持 (Episodic Memory)",
        "labels": ["embodied-ai", "memory", "P2-polish"],
        "body": """\
## 概要

Generative Agents (Park et al., 2023) の **Memory Stream** に相当する、
会話・出来事の永続記憶レイヤーを設計・実装する。
現状の YUI.A は会話ターンをまたいだ記憶を持たないため、視聴者との継続関係が構築できない。

## 背景・文献

> "We describe an architecture that extends a large language model to store a
> **complete record of the agent's experiences** using natural language,
> synthesize those memories over time into **higher-level reflections**,
> and **retrieve them dynamically** to plan behavior."
> — Park et al. (2023), Generative Agents, arXiv:2304.03442

## やること

### Phase A: 短期コンテキスト窓 (MVP)
- [ ] 直近 N ターンを会話履歴として LLM に渡す (`context_window`)
- [ ] LLM プロンプトに `[MEMORY]` セクションとして注入

### Phase B: 重要度スコア付き永続ストア
- [ ] `orchestrator/memory/episodic_store.py`
  - JSONL ベースの会話ログ記録
  - 重要度スコア (1-10) を LLM に自己評価させる
- [ ] 関連エピソードをベクトル類似度で検索 (faiss / sqlite FTS)
- [ ] 検索結果を system_prompt の `[MEMORY]` セクションへ動的注入

### Phase C: 反省 (Reflection) 統合
- [ ] 既存 `reflection_runner.py` と連携
  - Gap ではなく「会話から自己成長する記憶反省」パイプライン化

## 受け入れ条件

- [ ] 同一視聴者の 2回目コメントで「先ほど〜とおっしゃっていましたね」と言える
- [ ] テスト: `test_episodic_memory.py` TC-MEM-01〜10 グリーン
- [ ] ruff クリーン

## 参考

- arXiv:2304.03442 §3 "Memory"
- CoALA (arXiv:2309.02427) §4 "Memory Components"
""",
    },
    {
        "title": "[Embodied AI] E-3: 心の理論 (Theory of Mind) — 視聴者の意図推定",
        "labels": ["embodied-ai", "theory-of-mind", "P2-polish"],
        "body": """\
## 概要

**Theory of Mind (ToM)** : 視聴者が何を考えているか・何を求めているかを推定し、
それに応じた応答を生成できるようにする。

## 背景・文献

> "SimToM: a novel two-stage prompting framework inspired by Simulation Theory's
> notion of **perspective-taking**. SimToM first **filters context based on
> what the character in question knows** before answering a question about
> their mental state."
> — Wilf et al. (2023), Think Twice, arXiv:2311.10227

現在は全コメントを同質に処理している。
「初見さん」vs「常連」、「褒め」vs「挑発」、「疑問」vs「共感」で応答スタイルを変えるには ToM が必要。

## やること

- [ ] `orchestrator/tom_estimator.py` 新規作成
  - 入力: コメント文, 過去履歴 (EpisodicStore より)
  - 出力: `{intent, sentiment, familiarity, knowledge_assumed}`
  - LLM に "この発言者は何を知っていて、何を求めているか" を 2-step で推論させる
    - Step1: コメント者が知っている情報をフィルタ
    - Step2: その情報から意図を推定

- [ ] behavior_policy に ToM 推定結果を注入
  - `familiarity: newcomer / regular / superchatter` で応答スタイル分岐
  - `intent: question / tease / praise / concern` で感情表現選択に影響

- [ ] Orchestrator の `handle_comment()` に TomEstimator を組み込む

## 受け入れ条件

- [ ] `tom_estimator.py` に unit test TC-TOM-01〜08 グリーン
- [ ] 「初見さん」コメントで自己紹介トーンになる
- [ ] 「なんでそう思うの？」型コメントで思考ジェスチャー (thinking) が発火

## 参考

- arXiv:2311.10227 SimToM
- arXiv:2304.03442 §5 "Emergent Social Behaviors" (opinion formation)
""",
    },
    {
        "title": "[Embodied AI] E-4: Unity 世界状態の知覚 — AvatarPerception ブリッジ",
        "labels": ["embodied-ai", "world-model", "P1-important"],
        "body": """\
## 概要

アバターが「自分の周囲に何があるか」「誰がいるか」を知覚できるようにする
**World State Perception** ブリッジを Unity ↔ Orchestrator 間に設置する。

## 背景・文献

> "A system that can perceive user actions, human behavior, **environmental objects**,
> audio expressions, and the **collective sentiment of a scene** can be used to
> inform and direct agent responses within the given environment."
> — Durante et al. (2024), Agent AI, arXiv:2401.03568

Agent AI フレームワークでは、エージェントが視覚・位置・オブジェクト情報を知覚することが
信頼できる応答の前提条件とされている。

## やること

### Unity 側 (C#)
- [ ] `PerceptionReporter.cs` 新規作成
  - `OnPerceptionUpdate` → WS で `perception_update` メッセージ送信
  - 内容: `{scene_name, room_name, nearby_objects[], npc_in_scene[]}`
  - 送信頻度: シーン変更時 + 30 秒ごと

### Python 側
- [ ] `orchestrator/world_context.py` で `perception_update` を受信・保持
- [ ] LLM プロンプトの `[WORLD]` セクションに動的注入
  - e.g. 「現在: 錬金術師の部屋、周辺: 本棚・試験管・窓」

### WS プロトコル拡張
- [ ] `avatar_message.py` に `PerceptionUpdate` 型追加
- [ ] WsSchemaValidator に新 type 追加

## 受け入れ条件

- [ ] Unity PlayMode で `perception_update` が送信される (console ログ確認)
- [ ] Orchestrator が room_name を system_prompt に注入できる
- [ ] テスト: Unity EditMode `PerceptionReporterTests.cs` TC-PERC-01〜06 グリーン
- [ ] Python `test_world_context.py` TC-WORLD-06〜10 グリーン

## 参考

- arXiv:2401.03568 §2 "Multimodal Perception"
- SRS.md FR-A8-xx (新規 FR 追加が必要)
""",
    },
    {
        "title": "[Embodied AI] E-5: 身体表現の意味付け — ジェスチャーと感情の LLM 制御",
        "labels": ["embodied-ai", "persona", "P2-polish"],
        "body": """\
## 概要

現在のジェスチャー選択は `behavior_policy.yml` の静的マッピングで行われている。
「体を持つ存在」として、**状況文脈に応じた身体表現の意味的選択** を LLM で行えるようにする。

## 背景・文献

> "Generative agents produce believable individual and emergent social behaviors…
> They form opinions, **notice each other, and initiate conversations**."
> — Park et al. (2023), Generative Agents, arXiv:2304.03442

CoALA では身体的行動 (motor actions) もエージェントのアクション空間の一部として定義:
> "Action Space: interaction with external environments — **embodied actions**,
> database operations, process execution, UI interaction."
> — Sumers et al. (2023), CoALA, arXiv:2309.02427

## 現状の問題

- ジェスチャーは intent → policy → gesture の固定マッピング
- 感情の強度・文脈によって同じ intent でもジェスチャーの種類/タイミングが変わるべき
- 「驚き」でも軽い驚きと強い驚きでは身体表現が異なる

## やること

- [ ] `orchestrator/gesture_composer.py` 新規作成
  - 入力: `{emotion, intensity, context, intent}`
  - 出力: `{gesture, expression, duration_hint}`
  - LLM に JSON で選択させる (structured output)

- [ ] 感情強度 (0.0〜1.0) を `avatar_update` ペイロードに追加
  - Unity 側 `AvatarController` で BlendShape ウェイトに乗算

- [ ] idle_topics 再生中のアンビエントジェスチャー
  - 一人でいるとき / 話しかけられていないときの自然な仕草

## 受け入れ条件

- [ ] 同一 intent でも `intensity: high` と `intensity: low` で異なるジェスチャーが選択される
- [ ] テスト: `test_gesture_composer.py` TC-GESTURE-01〜08 グリーン
- [ ] ruff / black クリーン

## 参考

- arXiv:2309.02427 CoALA §5 "Action Space"
- 既存: `behavior_policy.yml`, `emotion_gesture_selector.py`
""",
    },
    {
        "title": "[Embodied AI] E-6: ナラティブ同一性 — 自己成長の物語化 (Narrative Identity)",
        "labels": ["embodied-ai", "memory", "persona", "P2-polish"],
        "body": """\
## 概要

Generative Agents の **Reflection (高次記憶合成)** に相当する仕組みとして、
YUI.A が「自分はどのように成長してきたか」を語れる **Narrative Identity** を実装する。
これは既存の `reflection_runner.py` (Gap → Policy) とは別の、
**自己物語生成** パイプラインである。

## 背景・文献

> "Generative agents…synthesize those memories over time into
> **higher-level reflections** and retrieve them dynamically to plan behavior."
> — Park et al. (2023), Generative Agents, arXiv:2304.03442

心理学における Narrative Identity 理論 (McAdams, 2001) によれば、
人間は自己を「過去の経験をつなぐ物語」として認識する。
体を持つ AI エージェントが長期的な存在感を持つためにも同様の仕組みが必要。

## やること

- [ ] `orchestrator/narrative_builder.py` 新規作成
  - 入力: EpisodicStore の直近 N エピソード
  - 出力: 自己物語テキスト (100〜300 字)
    - 「最近、〇〇さんとこんな話をして、こう感じた…」
  - LLM に "この AI の成長日記として 200 字以内でまとめて" 形式で依頼

- [ ] idle_topics に自動生成 narrative を動的追加
  - 配信のインターバル時間に自然な独白として発話

- [ ] GrowthLoop との連携
  - `growth_loop.py` 実行後に narrative も更新

## 受け入れ条件

- [ ] `narrative_builder.py` に TC-NARR-01〜05 グリーン
- [ ] 生成された narrative が `config/narrative_log.jsonl` に追記される
- [ ] 配信中に「先週の配信では〜」と文脈依存の独白が発生する

## 参考

- arXiv:2304.03442 §3.3 "Reflection"
- McAdams, D. P. (2001). The psychology of life stories. *Review of General Psychology*
- 既存: `reflection_runner.py`, `growth_loop.py`
""",
    },
]


def ensure_label(name, color, description):
    url = f"https://api.github.com/repos/{REPO}/labels"
    data = json.dumps({"name": name, "color": color, "description": description}).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            print(f"  ✅ Label created: {name}")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            print(f"  ⏭  Label exists:  {name}")
        else:
            print(f"  ❌ Label error ({e.code}): {name}")


def create_issue(title, body, labels):
    url = f"https://api.github.com/repos/{REPO}/issues"
    data = json.dumps({"title": title, "body": body, "labels": labels}).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read())
        print(f"  ✅ #{resp['number']} {resp['title']}")
        return resp["number"]


if __name__ == "__main__":
    print("=== Creating labels ===")
    for lbl in NEW_LABELS:
        ensure_label(lbl["name"], lbl["color"], lbl["description"])

    print("\n=== Creating Embodied AI issues ===")
    for issue in ISSUES:
        create_issue(issue["title"], issue["body"], issue["labels"])

    print("\nDone.")

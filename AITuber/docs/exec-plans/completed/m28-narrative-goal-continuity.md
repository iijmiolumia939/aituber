# M28: Narrative and Goal Continuity exec-plan

> **作成**: 2026-03-14
> **完了**: 2026-03-14
> **目標**: medium-horizon goal memory を追加し、narrative と life scheduler に continuity を流し込む
> **関連**: FR-GOAL-MEM-01, FR-E6-01, FR-LIFE-01, PLANS.md M28, autonomous-growth.md Runtime Memory Layers
> **依存**: M26 完了, M27 初期実装完了

---

## ゴール

短期の会話反応だけでなく、「最近この話題を深めたい」「この流れを続けたい」を runtime に残し、idle talk・narrative・life activity に薄く反映させる。

**Done の定義:**
- `goal_memory.py` が file-backed medium-horizon goal store として動作する
- reply path に `[GOALS]` block が注入される
- `NarrativeBuilder` が semantic/goal continuity を prompt と fallback に反映する
- `LifeScheduler` が medium-horizon goal focus を軽く受け取れる
- targeted pytest と changed-files quality gate が通る

---

## スコープ

| 含む | 含まない |
|---|---|
| repeated topic からの learning goal | embeddings/vector DB |
| reply path への `[GOALS]` 注入 | contradiction checker |
| NarrativeBuilder への semantic/goal fragment 注入 | heavy planning engine |
| LifeScheduler の軽量 goal bias | full BDI planner |

---

## 設計決定ログ

### 2026-03-14: M28 初期版は learning-goal のみ実装

goal continuity を広げすぎると scheduler instability を招く。
初期版では repeated topic から生成する `learning` focus のみを導入し、READ/TINKER/PONDER を中心に軽く bias する。

### 2026-03-14: narrative continuity は prompt と fallback の双方で反映

LLM が unavailable なときでも continuity が落ちないよう、NarrativeBuilder fallback にも semantic/goal hint を入れる。

---

## タスクブレークダウン

- [x] `orchestrator/goal_memory.py` 新設
- [x] repeated topic から medium-horizon goal を生成
- [x] `main.py` reply path へ `[GOALS]` 注入
- [x] `NarrativeBuilder` へ semantic/goal continuity 注入
- [x] `LifeScheduler` へ goal focus bias 追加
- [x] `behavior_completed` 成功 / 失敗イベントを GoalMemory に反映
- [x] follow-up goal を conversation から抽出
- [x] idle talk 向け hint selection を compact 化
- [x] viewer 単位の follow-up goal 優先度を追加
- [x] narrative fallback で上位 2 goal lines を使用
- [x] familiarity を goal priority に反映
- [x] narrative loop に goal-aware episodic selection を追加
- [x] narrative recall に viewer continuity を反映
- [x] `[FACTS]` / `[GOALS]` の重複 topic を軽く削減
- [x] narrative / reply recall に time_bucket / room_name を反映
- [x] `[FACTS]` と `[GOALS]` の責務分離を生成段階にも反映
- [x] narrative / reply / behavior memory に scene_name continuity を反映
- [x] nearby object continuity を episodic recall に反映
- [x] `tests/test_goal_memory.py` 新設
- [x] `tests/test_narrative_builder.py` / `tests/test_life_scheduler.py` / `tests/test_orchestrator.py` 拡張
- [x] targeted pytest + changed-files quality gate

---

## 進捗ログ

### 2026-03-14

`GoalMemory` を追加し、会話で繰り返された topic を medium-horizon な learning goal として保存する基盤を入れた。
reply path では `[GOALS]` block を注入し、idle hint と scheduler focus にも同じ goal continuity を流すようにした。
`NarrativeBuilder` は semantic facts と goals を prompt/fallback の両方で参照できるようにした。
加えて、`behavior_completed` の成功 / 失敗イベントも social / exploration 系の goal continuity に反映するようにした。残作業は targeted validation と quality gate。

その後、`続き` 系の発話から `follow_up_goal` を抽出し、topic の継続スレッド自体を medium-horizon goal として保持するようにした。idle talk では goal/life/narrative hint をそのまま全部積まず、現在性の高いものを最大 2 件まで選ぶ compact selection を導入した。
さらに `follow_up_goal` は viewer ごとの subject を持つようにし、reply prompt では同じ視聴者の continuation goal を優先するようにした。`NarrativeBuilder` fallback も goal line を 1 本だけではなく上位 2 本まで扱い、自己物語の変化量を少し上げた。
最後に、SemanticMemory の familiarity score を goal priority に渡し、常連との継続スレッドを newcomer より強く優先するようにした。narrative loop でも top goals を query にして episodic recall を引き、最近順だけでなく goal-relevant な記憶を自己物語へ流し込むようにした。
そのうえで narrative recall には goal subject を author continuity として渡し、特定視聴者との継続スレッドを自己物語へ反映しやすくした。reply prompt では `[FACTS]` と `[GOALS]` の重複 topic line を薄く削り、viewer profile のような非重複情報だけを残す構成にした。
加えて episodic recall には ambient context として `time_bucket` と `room_name` も渡し、同じ話題でも現在の場所や時間帯に近い記憶を優先するようにした。これで narrative loop は goal-aware / viewer-aware に加えて scene-aware に近い想起ができる。
さらに semantic fragment 側に `exclude_topics` を導入し、active goal と同じ thread は `[FACTS]` 生成時点で落とすようにした。これで `[FACTS]` は viewer relationship / background preference に寄り、`[GOALS]` は今まさに深めたい thread に寄る構造になった。
その後、episodic metadata に `scene_name` も通し、conversation reply・behavior completion・narrative recall のすべてで scene continuity を使えるようにした。同じ room 名でも scene が違う場合の取り違えを減らすための一段深い環境コンテキストである。
加えて `objects_nearby` も小さな token list として episodic metadata に載せ、現在の周辺オブジェクトと重なる記憶をわずかに優先するようにした。scene/room と同じく grounding signal だが、保持量は最大 5 件に絞って prompt/JSONL の肥大化を避けている。
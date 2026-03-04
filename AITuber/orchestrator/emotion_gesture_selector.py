"""Response-based emotion and gesture selector.

Analyses YUI.A's LLM reply text and picks an appropriate Emotion + Gesture pair
using lightweight keyword rules.  No external calls; O(n) in text length.

Rules are ordered by priority (first match wins).
"""

from __future__ import annotations

import random

from orchestrator.avatar_ws import Emotion, Gesture

# ── Rule table ────────────────────────────────────────────────────────
# Each rule = (keywords_set, Emotion, gesture_candidates)
# gesture_candidates: list of Gesture — one is chosen at random if weight > 1
# Rules are checked in order; first match determines output.

_RULES: list[tuple[frozenset[str], Emotion, list[Gesture]]] = [
    # ── Greeting ──────────────────────────────────────────────────
    (frozenset(["こんにちは", "こんばんは", "おはよう", "はじめまして", "よろしく", "またね",
                "さようなら", "おつかれ", "ありがとう"]),
     Emotion.HAPPY, [Gesture.WAVE]),

    # ── Very excited / cheer ──────────────────────────────────────
    (frozenset(["やったー", "わーい", "最高", "サイコー", "すご！", "うれしい", "嬉しい",
                "大好き", "楽しい", "楽しかった", "かわいい", "可愛い", "素敵", "いいね",
                "いい！", "好き", "やった", "やばい", "やば"]),
     Emotion.HAPPY, [Gesture.CHEER, Gesture.WAVE]),

    # ── Surprised ─────────────────────────────────────────────────
    (frozenset(["え！", "えっ", "えー", "まじ", "まじで", "マジ", "マジで",
                "びっくり", "驚き", "なんと", "うそ", "うそー",
                "信じられない", "ほんとに", "ほんと！"]),
     Emotion.SURPRISED, [Gesture.NONE]),

    # ── Agreement / nod ───────────────────────────────────────────
    (frozenset(["そうそう", "だよね", "わかる", "確かに", "なるほど",
                "その通り", "おっしゃる通り", "同意", "うんうん", "うん"]),
     Emotion.HAPPY, [Gesture.NOD]),

    # ── Thinking / pondering ──────────────────────────────────────
    (frozenset(["うーん", "えーと", "えっと", "難しい", "むずかしい",
                "考えてみる", "考えると", "どうだろう", "そうだなぁ", "そうだな",
                "ちょっと考え", "むずかし"]),
     Emotion.THINKING, [Gesture.NONE]),

    # ── Sad / apology ─────────────────────────────────────────────
    (frozenset(["悲しい", "つらい", "ごめん", "ごめんね", "申し訳",
                "残念", "残念だな", "残念ながら"]),
     Emotion.SAD, [Gesture.SHRUG, Gesture.SAD_IDLE]),

    # ── Refusal / can't help ──────────────────────────────────────
    (frozenset(["できないな", "できません", "わからない", "わからないな",
                "教えられない", "難しいね"]),
     Emotion.NEUTRAL, [Gesture.SHRUG]),

    # ── Playful / teasing ─────────────────────────────────────────
    (frozenset(["あはは", "ふふ", "ふふふ", "くすくす", "笑", "ｗ", "w",
                "冗談", "冗談だよ", "嘘だよ", "うそだよ"]),
     Emotion.HAPPY, [Gesture.LAUGH, Gesture.CHEER, Gesture.SIT_LAUGH]),

    # ── Shy / embarrassed ─────────────────────────────────────────
    (frozenset(["恥ずかしい", "はずかしい", "照れ", "てれ", "えへ",
                "もう", "やだ", "ドキドキ"]),
     Emotion.HAPPY, [Gesture.SHY]),

    # ── Rejected / can't / tough ──────────────────────────────────
    (frozenset(["むり", "無理", "できない", "たいへん", "大変",
                "つらい", "厳しい", "きつい"]),
     Emotion.SAD, [Gesture.REJECTED, Gesture.SIGH]),

    # ── Sigh / resignation ────────────────────────────────────────
    (frozenset(["はぁ", "はあ", "ため息", "やれやれ", "ふぅ", "ふう",
                "まあいいか", "しょうがない"]),
     Emotion.SAD, [Gesture.SIGH]),

    # ── Thankful ──────────────────────────────────────────────────
    (frozenset(["ありがとう", "感謝", "うれしいな", "助かった",
                "おかげ", "よかった"]),
     Emotion.HAPPY, [Gesture.THANKFUL, Gesture.WAVE]),

    # ── Pointing / explaining ─────────────────────────────────────
    (frozenset(["つまり", "要するに", "ポイントは", "大事なのは",
                "注目して", "見て", "ここが", "実は"]),
     Emotion.NEUTRAL, [Gesture.SIT_POINT]),

    # ── Clapping / celebrating ────────────────────────────────────
    (frozenset(["おめでとう", "おめでとございます", "すばらしい", "素晴らしい",
                "パチパチ", "拍手"]),
     Emotion.HAPPY, [Gesture.SIT_CLAP, Gesture.CHEER]),

    # ── Disbelief / doubt ─────────────────────────────────────────
    (frozenset(["信じられない", "ありえない", "まさか", "本当に？",
                "ほんとに？", "うそ！", "うそでしょ"]),
     Emotion.SURPRISED, [Gesture.SIT_DISBELIEF]),

    # ── Frustrated / kick / rebellious ───────────────────────────
    (frozenset(["もう！", "むかつく", "イライラ", "腹立つ",
                "やめてよ", "ちょっと！"]),
     Emotion.SAD, [Gesture.SAD_KICK, Gesture.SIT_KICK]),

    # ── Surprised (exclamation) ───────────────────────────────────
    (frozenset(["すごい", "スゴイ", "すごっ", "ほんと！", "えええ",
                "うわ", "うわー", "さすが"]),
     Emotion.SURPRISED, [Gesture.SURPRISED]),

    # ── Deep thinking ─────────────────────────────────────────────
    (frozenset(["考えてみよう", "そうかもしれない", "もしかしたら",
                "仮に", "例えば", "どうだろう"]),
     Emotion.THINKING, [Gesture.THINKING]),
]


def select_emotion_gesture(response_text: str) -> tuple[Emotion, Gesture]:
    """Return (Emotion, Gesture) appropriate for *response_text*.

    Matches in-order rules; defaults to NEUTRAL + NOD when no rule fires.
    """
    for keywords, emotion, gestures in _RULES:
        if any(kw in response_text for kw in keywords):
            return emotion, random.choice(gestures)
    return Emotion.NEUTRAL, Gesture.NOD


# ── Convenience: select for idle talk ────────────────────────────────

def select_idle_emotion_gesture(topic_hint: str | None = None) -> tuple[Emotion, Gesture]:
    """Emotion + gesture for idle/self-initiated talk.

    キーワードマッチが外れた場合は HAPPY + アイドル系ジェスチャーをランダム選択。
    """
    if topic_hint:
        emotion, gesture = select_emotion_gesture(topic_hint)
        if emotion != Emotion.NEUTRAL:
            return emotion, gesture
    # アイドルトーク用バリエーション（会話が弾んでいる感を出す）
    idle_candidates = [
        Gesture.WAVE,
        Gesture.NOD,
        Gesture.CHEER,
        Gesture.IDLE_ALT,
    ]
    return Emotion.HAPPY, random.choice(idle_candidates)

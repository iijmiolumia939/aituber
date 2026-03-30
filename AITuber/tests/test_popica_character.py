"""TC-POPICA-CHAR-01 〜 TC-POPICA-IDLE-03: 天導ルミナ キャラクター設定テスト.

popica.yml の構成を検証する:
  - 音声設定 (ユーレイちゃん 甘々 / speaker_id=103)
  - system prompt のキーワード
  - idle_topics の件数・カテゴリカバレッジ
  - template_responses の件数
  - intents セクションの構成

SRS refs: FR-A1-01, FR-CHAR-01.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.character import load_character

_POPICA_YML = Path(__file__).parent.parent / "config" / "characters" / "popica.yml"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def popica_raw() -> dict:
    """popica.yml の生 YAML データ。"""
    with open(_POPICA_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def popica():
    """load_character で読み込んだ CharacterConfig。"""
    return load_character("popica")


# ── TC-POPICA-CHAR-01: load_character("popica") で正しくロードされる ──────


def test_load_character_by_name(popica) -> None:
    """TC-POPICA-CHAR-01: load_character('popica') で天導ルミナがロードされる。"""
    assert popica.name == "天導 ルミナ"


# ── TC-POPICA-CHAR-02: voice.speaker_id=103 (ユーレイちゃん 甘々) ────────


def test_voice_speaker_id(popica) -> None:
    """TC-POPICA-CHAR-02: speaker_id=103 (ユーレイちゃん 甘々) が設定されている。"""
    assert popica.voice.speaker_id == 103
    assert popica.voice.tts_backend == "voicevox"


# ── TC-POPICA-CHAR-03: system_prompt に王道かわいい系キーワードが含まれる ──


def test_system_prompt_character_keywords(popica) -> None:
    """TC-POPICA-CHAR-03: system_prompt にルミナ固有キーワードが含まれる。"""
    prompt = popica.system_prompt
    assert "天導 ルミナ" in prompt
    assert "かわいい" in prompt
    assert "雑談" in prompt


# ── TC-POPICA-CHAR-04: 一人称「わたし」が system_prompt に含まれる ────────


def test_system_prompt_first_person(popica) -> None:
    """TC-POPICA-CHAR-04: system_prompt に一人称「わたし」の記述が含まれる。"""
    assert "わたし" in popica.system_prompt


# ── TC-POPICA-CHAR-05: 日本語のみルールが traits に含まれる ──────────────


def test_japanese_only_trait(popica_raw) -> None:
    """TC-POPICA-CHAR-05: traits に日本語のみの制約が含まれる。"""
    traits = popica_raw["personality"]["traits"]
    assert any("日本語のみ" in t for t in traits)


# ── TC-POPICA-TPL-01: template_responses が 4件以上存在する ──────────────


def test_template_responses_count(popica) -> None:
    """TC-POPICA-TPL-01: template_responses が 4件以上定義されている。"""
    assert len(popica.template_responses) >= 4


# ── TC-POPICA-TPL-02: template_responses に絵文字が含まれない ────────────


def test_template_responses_no_emoji(popica) -> None:
    """TC-POPICA-TPL-02: template_responses に絵文字が含まれない (音声読み上げ対応)。"""
    import re

    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0\U0000FE0F]"
    )
    for resp in popica.template_responses:
        assert not emoji_pattern.search(resp), f"テンプレに絵文字が含まれる: {resp}"


# ── TC-POPICA-IDLE-01: idle_topics が 10件以上存在する ────────────────────


def test_idle_topics_count(popica) -> None:
    """TC-POPICA-IDLE-01: idle_topics が 10件以上（記憶+時事+定番の混合）。"""
    assert len(popica.idle_topics) >= 10


# ── TC-POPICA-IDLE-02: idle_topics に短期・中期・長期記憶系の話題が含まれる


def test_idle_topics_memory_coverage(popica_raw) -> None:
    """TC-POPICA-IDLE-02: idle_topics が記憶レイヤー系のヒントを含む。"""
    topics = popica_raw["idle_topics"]
    topics_text = "\n".join(topics)
    # 短期記憶系 (直近・さっき・今日 etc.)
    assert any(
        kw in topics_text for kw in ("さっき", "直近", "今日")
    ), "短期記憶系のトピックが見つからない"
    # 中期記憶系 (常連・テーマ・フォローアップ etc.)
    assert any(
        kw in topics_text for kw in ("常連", "テーマ", "フォローアップ")
    ), "中期記憶系のトピックが見つからない"
    # 長期記憶系 (振り返り・成長・思い出 etc.)
    assert any(
        kw in topics_text for kw in ("振り返", "成長", "思い出")
    ), "長期記憶系のトピックが見つからない"


# ── TC-POPICA-IDLE-03: idle_topics に時事・季節系の話題が含まれる ────────


def test_idle_topics_current_events(popica_raw) -> None:
    """TC-POPICA-IDLE-03: idle_topics に時事・季節系のヒントが含まれる。"""
    topics = popica_raw["idle_topics"]
    topics_text = "\n".join(topics)
    assert any(
        kw in topics_text for kw in ("季節", "話題", "何の日")
    ), "時事・季節系のトピックが見つからない"


# ── TC-POPICA-INT-01: intents セクションに必須 intent が定義されている ────


_EXPECTED_INTENTS = ["broadcast_start", "broadcast_stop", "camera_switch", "check_self_view"]


@pytest.mark.parametrize("intent_name", _EXPECTED_INTENTS)
def test_intent_exists(intent_name: str, popica_raw) -> None:
    """TC-POPICA-INT-01: 各 intent が popica.yml の intents に存在する。"""
    intents = popica_raw.get("intents", [])
    intent_names = [i["intent"] for i in intents]
    assert intent_name in intent_names, f"intent '{intent_name}' が popica.yml に存在しない"


# ── TC-POPICA-INT-02: 各 intent に action と patterns が定義されている ────


@pytest.mark.parametrize("intent_name", _EXPECTED_INTENTS)
def test_intent_has_action_and_patterns(intent_name: str, popica_raw) -> None:
    """TC-POPICA-INT-02: 各 intent に action と patterns フィールドが存在する。"""
    intents = popica_raw.get("intents", [])
    entry = next((i for i in intents if i["intent"] == intent_name), None)
    assert entry is not None
    assert "action" in entry, f"'{intent_name}' に action がない"
    assert "patterns" in entry, f"'{intent_name}' に patterns がない"
    assert len(entry["patterns"]) >= 2, f"'{intent_name}' の patterns が2件未満"


# ── TC-POPICA-INT-03: broadcast intents のパターンが日本語 ───────────────


def test_broadcast_patterns_japanese(popica_raw) -> None:
    """TC-POPICA-INT-03: broadcast_start/stop のパターンが日本語で記述されている。"""
    intents = popica_raw.get("intents", [])
    for intent in intents:
        if intent["intent"] in ("broadcast_start", "broadcast_stop"):
            for pattern in intent["patterns"]:
                assert any(
                    "\u3040" <= ch <= "\u9fff" for ch in pattern
                ), f"パターン '{pattern}' に日本語文字が含まれない"


# ── TC-POPICA-YAML-01: YAML の構造整合性 ─────────────────────────────────


def test_yaml_structure(popica_raw) -> None:
    """TC-POPICA-YAML-01: popica.yml のトップレベル構造が正しい。"""
    assert "name" in popica_raw
    assert "voice" in popica_raw
    assert "personality" in popica_raw
    assert "response_rules" in popica_raw
    assert "template_responses" in popica_raw
    assert "idle_topics" in popica_raw
    assert "intents" in popica_raw


def test_personality_structure(popica_raw) -> None:
    """TC-POPICA-YAML-02: personality セクションに必須キーが揃っている。"""
    p = popica_raw["personality"]
    assert "traits" in p
    assert "first_person" in p
    assert "viewer_address" in p
    assert "speech_patterns" in p
    assert "style" in p

"""TC-YUIA-INT-01 〜 TC-YUIA-CHAR-07: YUI.A 世界観ブラッシュアップテスト.

M17: behavior_policy YUI.A 専用 intent 追加 + character system_prompt 統一

SRS refs: FR-A1-01, FR-CHAR-01.
TC refs:  TC-YUIA-INT-01〜06, TC-YUIA-CHAR-01〜07.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.character import load_character

# ── Paths ─────────────────────────────────────────────────────────────────

_POLICY_YML = Path(__file__).parent.parent / "Assets" / "StreamingAssets" / "behavior_policy.yml"
_YUIA_YML = Path(__file__).parent.parent / "config" / "characters" / "yuia.yml"

# ── YUI.A 専用 intent 一覧 (TC-YUIA-INT-01〜06) ─────────────────────────

_YUIA_INTENTS = [
    "record_observation",
    "analyze_data",
    "express_curiosity",
    "acknowledge_anomaly",
    "processing_lag",
    "scan_viewer",
]


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def policy_entries() -> list[dict]:
    """behavior_policy.yml の全エントリをパースして返す。"""
    with open(_POLICY_YML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # ファイルはトップレベルがリスト形式
    return [e for e in data if isinstance(e, dict) and "intent" in e]


@pytest.fixture(scope="module")
def policy_intent_map(policy_entries: list[dict]) -> dict[str, dict]:
    """intent 名 → エントリの辞書。"""
    return {e["intent"]: e for e in policy_entries if "intent" in e}


# ── TC-YUIA-INT-01〜06: 各 intent が behavior_policy.yml に存在する ──────


@pytest.mark.parametrize("intent_name", _YUIA_INTENTS)
def test_yuia_intent_exists_in_policy(
    intent_name: str, policy_intent_map: dict[str, dict]
) -> None:
    """TC-YUIA-INT-01〜06: 各 YUI.A 専用 intent が behavior_policy.yml に存在する。"""
    assert (
        intent_name in policy_intent_map
    ), f"YUI.A intent '{intent_name}' が behavior_policy.yml に存在しない。"


# ── TC-YUIA-INT-07: 各 intent に必須フィールドが含まれる ─────────────────


@pytest.mark.parametrize("intent_name", _YUIA_INTENTS)
def test_yuia_intent_has_required_fields(
    intent_name: str, policy_intent_map: dict[str, dict]
) -> None:
    """TC-YUIA-INT-07: 各 YUI.A intent に cmd + 動作フィールドが含まれる。"""
    entry = policy_intent_map[intent_name]
    assert "cmd" in entry, f"'{intent_name}' に cmd フィールドがない"
    # gesture / emotion / look_target / event のいずれか1つ以上が必要
    action_fields = {"gesture", "emotion", "look_target", "event"}
    has_action = any(f in entry for f in action_fields)
    assert has_action, f"'{intent_name}' に gesture/emotion/look_target/event のいずれも存在しない"


# ── TC-YUIA-INT-08: record_observation は nod + thinking を持つ ──────────


def test_record_observation_has_nod_and_thinking(policy_intent_map: dict[str, dict]) -> None:
    """TC-YUIA-INT-08: record_observation は gesture=nod かつ emotion=thinking。"""
    entry = policy_intent_map["record_observation"]
    assert entry.get("gesture") == "nod"
    assert entry.get("emotion") == "thinking"


# ── TC-YUIA-INT-09: acknowledge_anomaly は surprised を持つ ──────────────


def test_acknowledge_anomaly_has_surprised(policy_intent_map: dict[str, dict]) -> None:
    """TC-YUIA-INT-09: acknowledge_anomaly は emotion=surprised を持つ。"""
    entry = policy_intent_map["acknowledge_anomaly"]
    assert entry.get("emotion") == "surprised"


# ── TC-YUIA-CHAR-01: CHARACTER_NAME=yuia で yuia.yml がロードされる ────────


def test_load_character_env_yuia(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-YUIA-CHAR-01: CHARACTER_NAME=yuia 環境変数で yuia.yml がロードされる。"""
    monkeypatch.setenv("CHARACTER_NAME", "yuia")
    char = load_character()
    assert char.name == "YUI.A"
    assert char.voice.speaker_id == 47


# ── TC-YUIA-CHAR-02: 名前指定でロード ────────────────────────────────────


def test_load_character_by_name() -> None:
    """TC-YUIA-CHAR-02: load_character('yuia') で CharacterConfig が正しくロードされる。"""
    char = load_character("yuia")
    assert char.name == "YUI.A"
    assert char.voice.tts_backend == "voicevox"


# ── TC-YUIA-CHAR-03: system_prompt に観測AI 世界観が含まれる ──────────────


def test_yuia_system_prompt_contains_observation_ai() -> None:
    """TC-YUIA-CHAR-03: system_prompt に観測AI 固有キーワードが含まれる。"""
    char = load_character("yuia")
    prompt = char.system_prompt
    # 観察者・観測者の世界観
    assert "観測" in prompt, "system_prompt に '観測' キーワードがない"
    assert "データ" in prompt or "data" in prompt.lower(), "system_prompt に 'データ' がない"


# ── TC-YUIA-CHAR-04: 一人称「私」が system_prompt に含まれる ─────────────


def test_yuia_system_prompt_first_person() -> None:
    """TC-YUIA-CHAR-04: system_prompt に一人称「私」の記述が含まれる。"""
    char = load_character("yuia")
    assert "私" in char.system_prompt


# ── TC-YUIA-CHAR-05: idle_topics が空でない ───────────────────────────────


def test_yuia_idle_topics_not_empty() -> None:
    """TC-YUIA-CHAR-05: yuia.yml の idle_topics が最低5件存在する。"""
    char = load_character("yuia")
    assert (
        len(char.idle_topics) >= 5
    ), f"idle_topics が {len(char.idle_topics)} 件しかない (5件以上必要)"


# ── TC-YUIA-CHAR-06: template_responses が存在する ───────────────────────


def test_yuia_template_responses() -> None:
    """TC-YUIA-CHAR-06: yuia.yml に template_responses が4件以上定義されている。"""
    char = load_character("yuia")
    assert len(char.template_responses) >= 4


# ── TC-YUIA-CHAR-07: yuia.yml に voice.speaker_id=47 が設定されている ─────


def test_yuia_voice_speaker_id() -> None:
    """TC-YUIA-CHAR-07: yuia.yml の voice.speaker_id は 47 (ナースロボ＿タイプＴ)。"""
    char = load_character("yuia")
    assert char.voice.speaker_id == 47, f"期待 speaker_id=47, 実際={char.voice.speaker_id}"

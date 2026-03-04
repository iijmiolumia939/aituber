"""キャラクター設定モジュールのテスト。

character.py: load_character / _build_system_prompt / _default_character
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.character import (
    _build_system_prompt,
    _default_character,
    _default_idle_topics,
    _default_templates,
    load_character,
)


class TestBuildSystemPrompt:
    """_build_system_prompt のテスト。"""

    def test_minimal_data(self) -> None:
        prompt = _build_system_prompt({})
        assert "YUI.A" in prompt
        assert "## キャラクター設定" in prompt

    def test_custom_name(self) -> None:
        prompt = _build_system_prompt({"name": "テストちゃん"})
        assert "テストちゃん" in prompt
        assert "YUI.A" not in prompt

    def test_traits_included(self) -> None:
        data = {"personality": {"traits": ["明るい", "元気"]}}
        prompt = _build_system_prompt(data)
        assert "- 明るい" in prompt
        assert "- 元気" in prompt

    def test_first_person(self) -> None:
        data = {"personality": {"first_person": "ぼく"}}
        prompt = _build_system_prompt(data)
        assert "一人称は「ぼく」" in prompt

    def test_viewer_address(self) -> None:
        data = {"personality": {"viewer_address": ["みんな", "リスナー"]}}
        prompt = _build_system_prompt(data)
        assert "みんな」「リスナー" in prompt

    def test_speech_patterns(self) -> None:
        data = {"personality": {"speech_patterns": ["〜だよ！"], "style": "カジュアル"}}
        prompt = _build_system_prompt(data)
        assert "〜だよ！" in prompt
        assert "カジュアル" in prompt

    def test_response_rules(self) -> None:
        data = {"response_rules": ["日本語で回答する", "短く答える"]}
        prompt = _build_system_prompt(data)
        assert "## 応答ルール" in prompt
        assert "- 日本語で回答する" in prompt
        assert "- 短く答える" in prompt

    def test_full_config(self) -> None:
        data = {
            "name": "アキラ",
            "personality": {
                "traits": ["クール"],
                "first_person": "俺",
                "viewer_address": ["お前ら"],
                "speech_patterns": ["〜だぜ"],
                "style": "ぶっきらぼう",
            },
            "response_rules": ["短く答える"],
        }
        prompt = _build_system_prompt(data)
        assert "アキラ" in prompt
        assert "- クール" in prompt
        assert "一人称は「俺」" in prompt
        assert "お前ら" in prompt
        assert "〜だぜ" in prompt
        assert "ぶっきらぼう" in prompt
        assert "- 短く答える" in prompt


class TestDefaultCharacter:
    """デフォルトキャラクターのテスト。"""

    def test_has_name(self) -> None:
        char = _default_character()
        assert char.name == "YUI.A"

    def test_has_system_prompt(self) -> None:
        char = _default_character()
        assert len(char.system_prompt) > 0
        assert "YUI.A" in char.system_prompt

    def test_has_template_responses(self) -> None:
        char = _default_character()
        assert len(char.template_responses) >= 3

    def test_has_idle_topics(self) -> None:
        char = _default_character()
        assert len(char.idle_topics) >= 3


class TestDefaultHelpers:
    """_default_templates / _default_idle_topics のテスト。"""

    def test_templates_not_empty(self) -> None:
        assert len(_default_templates()) >= 3

    def test_idle_topics_not_empty(self) -> None:
        assert len(_default_idle_topics()) >= 3


class TestLoadCharacter:
    """load_character のテスト。"""

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        yml = tmp_path / "character.yml"
        yml.write_text(
            textwrap.dedent("""\
                name: "テスト太郎"
                personality:
                  traits:
                    - 冷静沈着
                  first_person: "僕"
                response_rules:
                  - 丁寧に答える
                template_responses:
                  - "テンプレ1"
                  - "テンプレ2"
                  - "テンプレ3"
                idle_topics:
                  - "何か話そう"
            """),
            encoding="utf-8",
        )
        char = load_character(str(yml))
        assert char.name == "テスト太郎"
        assert "テスト太郎" in char.system_prompt
        assert "冷静沈着" in char.system_prompt
        assert "僕" in char.system_prompt
        assert char.template_responses == ["テンプレ1", "テンプレ2", "テンプレ3"]
        assert char.idle_topics == ["何か話そう"]

    def test_missing_file_returns_default(self, tmp_path: Path) -> None:
        char = load_character(str(tmp_path / "nonexistent.yml"))
        assert char.name == "YUI.A"
        assert len(char.system_prompt) > 0

    def test_empty_yaml_returns_defaults(self, tmp_path: Path) -> None:
        yml = tmp_path / "empty.yml"
        yml.write_text("", encoding="utf-8")
        char = load_character(str(yml))
        assert char.name == "YUI.A"
        assert len(char.template_responses) >= 3
        assert len(char.idle_topics) >= 3

    def test_invalid_yaml_returns_defaults(self, tmp_path: Path) -> None:
        yml = tmp_path / "bad.yml"
        yml.write_text("[invalid yaml{{{", encoding="utf-8")
        char = load_character(str(yml))
        assert char.name == "YUI.A"

    def test_empty_templates_uses_defaults(self, tmp_path: Path) -> None:
        yml = tmp_path / "no_tpl.yml"
        yml.write_text(
            textwrap.dedent("""\
                name: "ノーテンプレ"
                template_responses: []
                idle_topics: []
            """),
            encoding="utf-8",
        )
        char = load_character(str(yml))
        assert char.name == "ノーテンプレ"
        # 空リストの場合はデフォルトが使われる
        assert len(char.template_responses) >= 3
        assert len(char.idle_topics) >= 3

    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yml = tmp_path / "env_char.yml"
        yml.write_text('name: "環境変数キャラ"', encoding="utf-8")
        monkeypatch.setenv("CHARACTER_CONFIG_PATH", str(yml))
        char = load_character()
        assert char.name == "環境変数キャラ"

    def test_loads_project_character_yml(self) -> None:
        """プロジェクトの config/character.yml が読み込める。"""
        project_yml = Path(__file__).parent.parent / "config" / "character.yml"
        if project_yml.exists():
            char = load_character(str(project_yml))
            assert char.name == "YUI.A"
            assert len(char.system_prompt) > 50

    def test_load_yuia_by_name(self) -> None:
        """TC-CHAR-10: `-c yuia` エントリポイント相当 — yuia.yml が正しくロードされる。

        FR-CHATID-AUTO-01 (character resolution path).
        Issue #6: キャラクター起動引数 `-c yuia` の動作確認.
        """
        char = load_character("yuia")
        assert char.name  # 空でない
        # yuia.yml が存在する場合は YUI.A の設定が適用される
        project_yuia = Path(__file__).parent.parent / "config" / "characters" / "yuia.yml"
        if project_yuia.exists():
            assert char.name == "YUI.A"
            assert len(char.system_prompt) > 50
            assert char.voice.speaker_id is not None
            assert len(char.idle_topics) >= 1

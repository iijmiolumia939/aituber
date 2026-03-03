"""マルチキャラクター / VoiceConfig のテスト。"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator.character import (
    VoiceConfig,
    _parse_voice_config,
    list_characters,
    load_character,
)


class TestVoiceConfig:
    """VoiceConfig データクラスのテスト。"""

    def test_defaults(self) -> None:
        v = VoiceConfig()
        assert v.tts_backend == "voicevox"
        assert v.speaker_id == 1
        assert v.tts_port is None
        assert v.sbv2_model_id == 0
        assert v.sbv2_style == "Neutral"

    def test_custom_values(self) -> None:
        v = VoiceConfig(
            tts_backend="style_bert_vits2",
            speaker_id=10,
            tts_port=5001,
            sbv2_model_id=3,
            sbv2_style="Happy",
        )
        assert v.tts_backend == "style_bert_vits2"
        assert v.speaker_id == 10
        assert v.tts_port == 5001


class TestParseVoiceConfig:
    """_parse_voice_config のテスト。"""

    def test_no_voice_section(self) -> None:
        v = _parse_voice_config({})
        assert v.tts_backend == "voicevox"
        assert v.speaker_id == 1

    def test_with_voice_section(self) -> None:
        data = {
            "voice": {
                "tts_backend": "style_bert_vits2",
                "speaker_id": 47,
                "tts_port": 5000,
                "sbv2_model_id": 2,
                "sbv2_style": "Angry",
            }
        }
        v = _parse_voice_config(data)
        assert v.tts_backend == "style_bert_vits2"
        assert v.speaker_id == 47
        assert v.tts_port == 5000
        assert v.sbv2_model_id == 2
        assert v.sbv2_style == "Angry"

    def test_partial_voice_section(self) -> None:
        data = {"voice": {"speaker_id": 99}}
        v = _parse_voice_config(data)
        assert v.speaker_id == 99
        assert v.tts_backend == "voicevox"  # default


class TestLoadCharacterWithVoice:
    """voice セクションを含む YAML のロードテスト。"""

    def test_voice_from_yaml(self, tmp_path: Path) -> None:
        yml = tmp_path / "voiced.yml"
        yml.write_text(
            textwrap.dedent("""\
                name: "ボイスキャラ"
                voice:
                  tts_backend: voicevox
                  speaker_id: 47
                personality:
                  traits:
                    - 明るい
                template_responses:
                  - "テスト応答"
                  - "テスト応答2"
                  - "テスト応答3"
            """),
            encoding="utf-8",
        )
        char = load_character(str(yml))
        assert char.name == "ボイスキャラ"
        assert char.voice.tts_backend == "voicevox"
        assert char.voice.speaker_id == 47

    def test_no_voice_section_uses_defaults(self, tmp_path: Path) -> None:
        yml = tmp_path / "novoice.yml"
        yml.write_text('name: "ノーボイス"', encoding="utf-8")
        char = load_character(str(yml))
        assert char.voice.tts_backend == "voicevox"
        assert char.voice.speaker_id == 1


class TestListCharacters:
    """list_characters のテスト。"""

    def test_lists_yml_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # config/characters を tmp_path に作成
        chars_dir = tmp_path / "config" / "characters"
        chars_dir.mkdir(parents=True)
        (chars_dir / "alpha.yml").write_text("name: Alpha")
        (chars_dir / "beta.yml").write_text("name: Beta")
        (chars_dir / "readme.txt").write_text("not a character")

        # character.py が参照するベースパスを差し替え
        import orchestrator.character as mod

        original_dir = mod._CHARACTERS_DIR
        monkeypatch.setattr(mod, "_CHARACTERS_DIR", "config/characters")

        # __file__.parent.parent = project root をモック
        original_file = mod.__file__
        monkeypatch.setattr(
            mod,
            "__file__",
            str(tmp_path / "orchestrator" / "character.py"),
        )

        result = list_characters()
        assert result == ["alpha", "beta"]

        monkeypatch.setattr(mod, "__file__", original_file)
        monkeypatch.setattr(mod, "_CHARACTERS_DIR", original_dir)

    def test_empty_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        chars_dir = tmp_path / "config" / "characters"
        chars_dir.mkdir(parents=True)

        import orchestrator.character as mod

        monkeypatch.setattr(
            mod,
            "__file__",
            str(tmp_path / "orchestrator" / "character.py"),
        )
        result = list_characters()
        assert result == []


class TestLoadCharacterByName:
    """名前指定でのキャラクターロードテスト。"""

    def test_load_by_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        chars_dir = tmp_path / "config" / "characters"
        chars_dir.mkdir(parents=True)
        (chars_dir / "testchar.yml").write_text(
            textwrap.dedent("""\
                name: "テストキャラ"
                voice:
                  speaker_id: 99
                template_responses:
                  - "a"
                  - "b"
                  - "c"
            """),
            encoding="utf-8",
        )

        import orchestrator.character as mod

        monkeypatch.setattr(
            mod,
            "__file__",
            str(tmp_path / "orchestrator" / "character.py"),
        )
        char = load_character("testchar")
        assert char.name == "テストキャラ"
        assert char.voice.speaker_id == 99

    def test_name_not_found_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # config/characters に該当なし、legacy も無い → デフォルト
        chars_dir = tmp_path / "config" / "characters"
        chars_dir.mkdir(parents=True)

        import orchestrator.character as mod

        monkeypatch.setattr(
            mod,
            "__file__",
            str(tmp_path / "orchestrator" / "character.py"),
        )
        char = load_character("nonexistent")
        assert char.name == "YUI.A"  # default

    def test_env_character_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        chars_dir = tmp_path / "config" / "characters"
        chars_dir.mkdir(parents=True)
        (chars_dir / "envchar.yml").write_text(
            textwrap.dedent("""\
                name: "環境キャラ"
                voice:
                  speaker_id: 55
                template_responses:
                  - "x"
                  - "y"
                  - "z"
            """),
            encoding="utf-8",
        )

        import orchestrator.character as mod

        monkeypatch.setattr(
            mod,
            "__file__",
            str(tmp_path / "orchestrator" / "character.py"),
        )
        monkeypatch.setenv("CHARACTER_NAME", "envchar")
        char = load_character()
        assert char.name == "環境キャラ"
        assert char.voice.speaker_id == 55

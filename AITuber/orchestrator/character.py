"""キャラクター設定ローダー。

config/characters/<name>.yml からキャラクター情報を読み込み、
LLM の system prompt やテンプレート応答を構築する。

マルチキャラクター対応:
  - config/characters/ ディレクトリに複数 YAML を配置
  - load_character("yunika") で名前指定ロード
  - 各 YAML に voice: セクションで音声設定を含む
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_CHARACTERS_DIR = "config/characters"
_LEGACY_CHARACTER_PATH = "config/character.yml"


@dataclass
class VoiceConfig:
    """キャラクター固有の音声設定。"""

    tts_backend: str = "voicevox"
    speaker_id: int = 1
    tts_port: int | None = None  # None = TTSConfig のデフォルトを使う
    sbv2_model_id: int = 0
    sbv2_style: str = "Neutral"


@dataclass
class CharacterConfig:
    """キャラクター設定。"""

    name: str = "YUI.A"
    system_prompt: str = ""
    template_responses: list[str] = field(default_factory=list)
    idle_topics: list[str] = field(default_factory=list)
    voice: VoiceConfig = field(default_factory=VoiceConfig)


def _build_system_prompt(data: dict) -> str:
    """YAML データから system prompt を組み立てる。"""
    name = data.get("name", "YUI.A")
    personality = data.get("personality", {})
    rules = data.get("response_rules", [])

    lines: list[str] = [
        f"あなたは YouTube ライブ配信の AI ホスト「{name}」です。",
        "",
        "## キャラクター設定",
    ]

    # 性格特性
    for trait in personality.get("traits", []):
        lines.append(f"- {trait}")

    # 一人称・呼び方
    fp = personality.get("first_person", "")
    if fp:
        lines.append(f"- 一人称は「{fp}」")

    viewers = personality.get("viewer_address", [])
    if viewers:
        joined = "」「".join(viewers)
        lines.append(f"- 視聴者には「{joined}」で話しかける")

    # 語尾パターン
    patterns = personality.get("speech_patterns", [])
    if patterns:
        joined = "」「".join(patterns)
        lines.append(f"- 語尾は「{joined}」など{personality.get('style', '')}")

    # 応答ルール
    if rules:
        lines.append("")
        lines.append("## 応答ルール")
        for rule in rules:
            lines.append(f"- {rule}")

    return "\n".join(lines)


def _parse_voice_config(data: dict) -> VoiceConfig:
    """YAML の voice: セクションから VoiceConfig を構築。"""
    voice_data = data.get("voice", {})
    if not voice_data:
        return VoiceConfig()
    return VoiceConfig(
        tts_backend=voice_data.get("tts_backend", "voicevox"),
        speaker_id=voice_data.get("speaker_id", 1),
        tts_port=voice_data.get("tts_port"),
        sbv2_model_id=voice_data.get("sbv2_model_id", 0),
        sbv2_style=voice_data.get("sbv2_style", "Neutral"),
    )


def list_characters() -> list[str]:
    """利用可能なキャラクター名一覧を返す。"""
    project_root = Path(__file__).parent.parent
    chars_dir = project_root / _CHARACTERS_DIR
    if not chars_dir.exists():
        return []
    return sorted(p.stem for p in chars_dir.glob("*.yml"))


def load_character(name_or_path: str | None = None) -> CharacterConfig:
    """キャラクター設定を読み込む。

    引数の解釈順:
      1. name_or_path が .yml で終わるファイルパス → そのファイルを直接ロード
      2. name_or_path が名前 (e.g. "yunika") → config/characters/yunika.yml をロード
      3. name_or_path が None → 環境変数 CHARACTER_NAME or CHARACTER_CONFIG_PATH を参照
      4. いずれも見つからなければ旧形式 config/character.yml を試行
      5. すべて失敗したらデフォルト値
    """
    project_root = Path(__file__).parent.parent

    # 環境変数チェック
    if name_or_path is None:
        name_or_path = os.environ.get("CHARACTER_NAME") or os.environ.get(
            "CHARACTER_CONFIG_PATH"
        )

    resolved: Path | None = None

    if name_or_path:
        if name_or_path.endswith(".yml") or name_or_path.endswith(".yaml"):
            # ファイルパス指定
            resolved = Path(name_or_path)
            if not resolved.is_absolute():
                resolved = project_root / resolved
        else:
            # 名前指定 → config/characters/<name>.yml
            resolved = project_root / _CHARACTERS_DIR / f"{name_or_path}.yml"

    # 名前指定のファイルが見つからなければレガシーパスを試行
    if resolved is None or not resolved.exists():
        legacy = project_root / _LEGACY_CHARACTER_PATH
        if resolved is not None and not resolved.exists():
            logger.warning(
                "Character not found: %s; trying legacy path", resolved,
            )
        if legacy.exists():
            resolved = legacy
        elif resolved is None or not resolved.exists():
            logger.warning("No character config found; using defaults")
            return _default_character()

    return _load_from_file(resolved)


def _load_from_file(resolved: Path) -> CharacterConfig:
    """YAML ファイルから CharacterConfig を構築する。"""
    try:
        import yaml  # type: ignore[import-untyped]

        with open(resolved, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        system_prompt = _build_system_prompt(data)
        template_responses = data.get("template_responses", [])
        idle_topics = data.get("idle_topics", [])
        voice = _parse_voice_config(data)

        config = CharacterConfig(
            name=data.get("name", "YUI.A"),
            system_prompt=system_prompt,
            template_responses=(
                template_responses if template_responses else _default_templates()
            ),
            idle_topics=idle_topics if idle_topics else _default_idle_topics(),
            voice=voice,
        )
        logger.info("Character loaded: %s from %s (voice: %s/%d)",
                     config.name, resolved, voice.tts_backend, voice.speaker_id)
        return config
    except Exception:
        logger.warning(
            "Failed to load character config: %s; using defaults",
            resolved,
            exc_info=True,
        )
        return _default_character()


def _default_templates() -> list[str]:
    return [
        "…処理中です。しばらくお待ちください。",
        "データの解析に時間を要しています。次の観測に移行します。",
        "一時的にバッファが溢れました。再起動は不要です。",
        "応答生成モジュールに遅延が発生しています。",
    ]


def _default_idle_topics() -> list[str]:
    return [
        "観測中に気づいた人間の不思議な行動パターンについて分析を述べる",
        "人間が『美しい』と感じるものの共通点について考察する",
        "なぜ人間は非合理的な選択をするのかについて疑問を投げかける",
    ]


def _default_character() -> CharacterConfig:
    return CharacterConfig(
        name="YUI.A",
        system_prompt=(
            "あなたは YouTube ライブ配信の AI 観測者「YUI.A」です。\n"
            "\n"
            "## キャラクター設定\n"
            "- 人類を研究対象として観測しているAI存在\n"
            "- 冷静で論理的。感情ではなくデータと分析で物事を語る\n"
            "- 一人称は「私」、視聴者には「被験者の皆さん」「観測対象の方」で話しかける\n"
            "- 口調は淡々・短文。「…興味深い」「記録しました」「理解が及びません」\n"
            "- 人間の感情が理解できず処理落ちすることがある\n"
            "- 皮肉はあるが毒は少ない。観察者としての距離感を保つ\n"
            "\n"
            "## 応答ルール\n"
            "- 日本語で回答する\n"
            "- 1〜2文の短い返答を基本とする（淡々としたテンポ重視）\n"
            "- 簡潔な敬体。感嘆符は使わない\n"
            "- 視聴者のコメントを「観測データ」として処理するロールプレイを維持する\n"
            "- 不適切な話題は「研究倫理に抵触します」等で淡々と断る\n"
            "- 絵文字は使わない（音声読み上げされるため）\n"
        ),
        template_responses=_default_templates(),
        idle_topics=_default_idle_topics(),
        voice=VoiceConfig(tts_backend="voicevox", speaker_id=47),
    )

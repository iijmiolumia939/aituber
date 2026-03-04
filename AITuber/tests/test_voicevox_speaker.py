"""VOICEVOX speaker_id=47 実機確認テスト。

TC-TTS-SPK-01: yuia.yml の speaker_id=47 が VOICEVOX に存在するか確認
TC-TTS-SPK-02: speaker_id=47 の音声名が "ナースロボ＿タイプＴ" であることを確認
TC-TTS-SPK-03: speaker_id=47 で音声合成クエリが成功するか確認

VOICEVOX が未起動の場合は自動スキップ (pytest.mark.skipif)。
CI では常にスキップされ、手動 ``pytest -m voicevox_live`` で実行。

SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02
"""

from __future__ import annotations

import httpx
import pytest
import yaml

VOICEVOX_URL = "http://127.0.0.1:50021"
YUIA_SPEAKER_ID = 47
# VOICEVOX 0.14+ における speaker_id=47 の期待値
EXPECTED_SPEAKER_NAME = "ナースロボ＿タイプＴ"


def _voicevox_available() -> bool:
    """VOICEVOX が起動しているか確認 (タイムアウト 2秒)。"""
    try:
        resp = httpx.get(f"{VOICEVOX_URL}/version", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _voicevox_available(),
    reason="VOICEVOX が起動していません (http://127.0.0.1:50021)。手動確認時のみ実行。",
)


# ── TC-TTS-SPK-01: speaker_id=47 が VOICEVOX に存在する ──────────────────────
def test_speaker_47_exists_in_voicevox() -> None:
    """TC-TTS-SPK-01: VOICEVOX /speakers に speaker_id=47 が存在すること。"""
    resp = httpx.get(f"{VOICEVOX_URL}/speakers", timeout=10.0)
    assert resp.status_code == 200, f"VOICEVOX /speakers 失敗: {resp.status_code}"

    speakers = resp.json()
    all_style_ids: list[int] = [style["id"] for sp in speakers for style in sp.get("styles", [])]
    assert YUIA_SPEAKER_ID in all_style_ids, (
        f"speaker_id={YUIA_SPEAKER_ID} が VOICEVOX に存在しません。"
        f"利用可能な ID: {sorted(all_style_ids)}"
    )


# ── TC-TTS-SPK-02: speaker_id=47 の名前が "ナースロボ＿タイプＴ" ─────────────
def test_speaker_47_name_is_nurse_robot() -> None:
    """TC-TTS-SPK-02: speaker_id=47 のキャラクター名が期待値と一致すること。"""
    resp = httpx.get(f"{VOICEVOX_URL}/speakers", timeout=10.0)
    speakers = resp.json()

    matched_name: str | None = None
    for sp in speakers:
        for style in sp.get("styles", []):
            if style["id"] == YUIA_SPEAKER_ID:
                matched_name = sp["name"]
                break

    assert matched_name is not None, f"speaker_id={YUIA_SPEAKER_ID} が見つかりません"
    assert EXPECTED_SPEAKER_NAME in matched_name or matched_name in EXPECTED_SPEAKER_NAME, (
        f"期待: '{EXPECTED_SPEAKER_NAME}', 実際: '{matched_name}'\n"
        f"yuia.yml の speaker_id を変更するか VOICEVOX のバージョンを確認してください。"
    )


# ── TC-TTS-SPK-03: speaker_id=47 で音声合成クエリが成功する ──────────────────
def test_speaker_47_audio_query_succeeds() -> None:
    """TC-TTS-SPK-03: speaker_id=47 で /audio_query が 200 を返すこと。"""
    resp = httpx.post(
        f"{VOICEVOX_URL}/audio_query",
        params={"text": "テスト", "speaker": YUIA_SPEAKER_ID},
        timeout=15.0,
    )
    assert (
        resp.status_code == 200
    ), f"audio_query 失敗 speaker_id={YUIA_SPEAKER_ID}: {resp.status_code} {resp.text[:200]}"
    query_data = resp.json()
    assert "accent_phrases" in query_data, "audio_query レスポンスに accent_phrases が無い"


# ── yuia.yml との整合性確認 ────────────────────────────────────────────────────
def test_yuia_yml_speaker_id_matches_voicevox() -> None:
    """TC-TTS-SPK-04: yuia.yml の speaker_id が VOICEVOX に実在すること。"""
    import pathlib

    yuia_yml = pathlib.Path(__file__).parent.parent / "config" / "characters" / "yuia.yml"
    assert yuia_yml.exists(), f"yuia.yml が見つかりません: {yuia_yml}"

    with yuia_yml.open(encoding="utf-8") as f:
        char = yaml.safe_load(f)

    yml_speaker_id = char["voice"]["speaker_id"]

    resp = httpx.get(f"{VOICEVOX_URL}/speakers", timeout=10.0)
    all_style_ids = [style["id"] for sp in resp.json() for style in sp.get("styles", [])]
    assert (
        yml_speaker_id in all_style_ids
    ), f"yuia.yml の speaker_id={yml_speaker_id} が VOICEVOX に存在しません"

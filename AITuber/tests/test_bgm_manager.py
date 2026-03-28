from __future__ import annotations

from orchestrator.bgm_manager import BGMConfig, BGMManager


class _FakeObsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def set_input_mute(self, source: str, mute: bool) -> None:
        self.calls.append((source, mute))


def test_switch_chat_unmutes_chat_and_mutes_others() -> None:
    cfg = BGMConfig(
        chat_source="chat",
        game_source="game",
        opening_source="opening",
        ending_source="ending",
    )
    bgm = BGMManager(cfg)
    obs = _FakeObsClient()

    bgm.switch(mode="chat", obs_client=obs)

    assert ("chat", False) in obs.calls
    assert ("game", True) in obs.calls
    assert ("opening", True) in obs.calls
    assert ("ending", True) in obs.calls


def test_switch_for_scene_maps_game_main() -> None:
    cfg = BGMConfig(chat_source="c", game_source="g", opening_source="o", ending_source="e")
    bgm = BGMManager(cfg)
    obs = _FakeObsClient()

    bgm.switch_for_scene(scene_name="Game_Main", obs_client=obs)

    assert ("g", False) in obs.calls

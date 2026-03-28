"""OBS BGM source switching helper."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BGMConfig:
    chat_source: str = "BGM_Chat"
    game_source: str = "BGM_Game"
    opening_source: str = "BGM_Opening"
    ending_source: str = "BGM_Ending"


class BGMManager:
    """Mute/unmute OBS BGM sources by scene mode."""

    def __init__(self, config: BGMConfig | None = None) -> None:
        self._cfg = config or BGMConfig(
            chat_source=os.environ.get("OBS_BGM_CHAT_SOURCE", "BGM_Chat"),
            game_source=os.environ.get("OBS_BGM_GAME_SOURCE", "BGM_Game"),
            opening_source=os.environ.get("OBS_BGM_OPENING_SOURCE", "BGM_Opening"),
            ending_source=os.environ.get("OBS_BGM_ENDING_SOURCE", "BGM_Ending"),
        )

    def _source_for_mode(self, mode: str) -> str | None:
        mode = (mode or "").lower()
        if mode == "chat":
            return self._cfg.chat_source
        if mode == "game":
            return self._cfg.game_source
        if mode == "opening":
            return self._cfg.opening_source
        if mode == "ending":
            return self._cfg.ending_source
        return None

    def switch(self, *, mode: str, obs_client: object) -> None:
        """Mute all managed BGM sources except mode target."""
        target = self._source_for_mode(mode)
        if not target:
            return

        set_input_mute = getattr(obs_client, "set_input_mute", None)
        if not callable(set_input_mute):
            logger.debug("OBS client has no set_input_mute; skip BGM switch")
            return

        sources = {
            self._cfg.chat_source,
            self._cfg.game_source,
            self._cfg.opening_source,
            self._cfg.ending_source,
        }

        for source in sources:
            try:
                set_input_mute(source, source != target)
            except Exception as exc:  # noqa: BLE001
                logger.debug("BGM mute update failed (%s): %s", source, exc)

    def switch_for_scene(self, *, scene_name: str, obs_client: object) -> None:
        scene_to_mode = {
            "Chat_Main": "chat",
            "Game_Main": "game",
            "Opening": "opening",
            "Ending": "ending",
        }
        mode = scene_to_mode.get(scene_name)
        if mode:
            self.switch(mode=mode, obs_client=obs_client)

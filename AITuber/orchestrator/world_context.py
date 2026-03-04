"""World context – situatedness and avatar self-perception.

FR-E1-01: Avatar retains awareness of its current scene, room, and environment.
FR-E4-01: Avatar receives perception_update messages from Unity and reflects them
          in LLM system prompt so responses feel grounded in the virtual world.

Issues: #11 E-1 Situatedness, #14 E-4 AvatarPerception
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WorldState:
    """Snapshot of the avatar's current perceived environment.

    FR-E1-01: Populated from Unity perception_update WS messages.
    """

    scene_name: str = ""
    """Unity シーン名 (例: "yuia_home")"""

    room_name: str = ""
    """ルーム/エリア名 (例: "living_room")"""

    objects_nearby: list[str] = field(default_factory=list)
    """周辺にあるオブジェクト名リスト"""

    time_of_day: str = ""
    """時刻帯 (例: "morning", "afternoon", "evening", "night")"""

    avatar_appearance: str = ""
    """アバターの現在の服装・見た目メモ (例: "casual_outfit_blue")"""

    updated_at: float = 0.0
    """最終更新時刻 (monotonic)"""


class WorldContext:
    """Maintains current world state and exposes it as an LLM prompt fragment.

    FR-E1-01, FR-E4-01.
    """

    _TIME_OF_DAY_JP: dict[str, str] = {
        "morning": "朝",
        "afternoon": "昼",
        "evening": "夕方",
        "night": "夜",
    }

    def __init__(self) -> None:
        self._state = WorldState()

    @property
    def state(self) -> WorldState:
        """現在の WorldState を返す（読み取り専用）。"""
        return self._state

    def update(self, msg: dict) -> None:
        """Parse a perception_update message from Unity and update state.

        FR-E4-01: Called by AvatarWSSender when it receives a
        ``perception_update`` message from the Unity client.

        Args:
            msg: Decoded JSON dict.  Expected fields (all optional):
                - scene_name: str
                - room_name: str
                - objects_nearby: list[str]
                - time_of_day: str
                - avatar_appearance: str
        """
        self._state = WorldState(
            scene_name=str(msg.get("scene_name", "") or ""),
            room_name=str(msg.get("room_name", "") or ""),
            objects_nearby=list(msg.get("objects_nearby", []) or []),
            time_of_day=str(msg.get("time_of_day", "") or ""),
            avatar_appearance=str(msg.get("avatar_appearance", "") or ""),
            updated_at=time.monotonic(),
        )
        logger.info(
            "[WorldContext] updated: scene=%s room=%s time=%s objects=%s",
            self._state.scene_name,
            self._state.room_name,
            self._state.time_of_day,
            self._state.objects_nearby,
        )

    def to_prompt_fragment(self) -> str:
        """Return a compact text block to inject into the LLM system prompt.

        FR-E1-01: Returns empty string when no scene is set.

        Example output::

            [WORLD]
            現在の場所: yuia_home/living_room
            時刻帯: 夕方
            周辺のもの: デスク, 窓, 本棚
        """
        if not self._state.scene_name:
            return ""

        lines: list[str] = []

        location = self._state.scene_name
        if self._state.room_name:
            location = f"{location}/{self._state.room_name}"
        lines.append(f"現在の場所: {location}")

        if self._state.time_of_day:
            tod_jp = self._TIME_OF_DAY_JP.get(self._state.time_of_day, self._state.time_of_day)
            lines.append(f"時刻帯: {tod_jp}")

        if self._state.objects_nearby:
            lines.append(f"周辺のもの: {', '.join(self._state.objects_nearby)}")

        if self._state.avatar_appearance:
            lines.append(f"見た目: {self._state.avatar_appearance}")

        return "[WORLD]\n" + "\n".join(lines)

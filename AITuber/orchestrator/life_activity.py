"""Daily Life Activity catalogue for autonomous avatar simulation.

Defines the vocabulary of Sims-like activities YUI.A performs
outside of active streaming sessions.

FR-LIFE-01: Autonomous daily life scheduler (non-streaming behaviour).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

# ── Activity types ────────────────────────────────────────────────────


class ActivityType(StrEnum):
    """Broad categories of daily life activity.

    FR-LIFE-01.
    """

    SLEEP = "sleep"  # 睡眠（深夜〜早朝）
    WAKE = "wake"  # 起床・朝の準備
    EAT = "eat"  # 食事（エネルギー補給）
    READ = "read"  # 読書・文献調査
    TINKER = "tinker"  # 作業・データ整理・研究
    WALK = "walk"  # 室内を歩き回る
    PONDER = "ponder"  # 深い思索・哲学
    STRETCH = "stretch"  # ストレッチ・メンテナンス
    IDLE = "idle"  # 特に何もしない


# ── Individual activity specification ────────────────────────────────


@dataclass(frozen=True)
class LifeActivity:
    """A single life activity with its avatar expression parameters.

    FR-LIFE-01.

    Attributes:
        activity_type: broad category.
        gesture: gesture key sent to AvatarController.
        emotion: emotion blendshape key.
        duration_sec: approximate real-world duration in seconds.
        look_target: "camera" | "down" | "random".
        room_id: optional room change (None = stay current).
        zone_id: optional zone move within the current room (None = stay current).
            e.g. "pc_area", "sleep_area", "relax_area"
        idle_hint: LLM hint string for idle talk while in this activity.
    """

    activity_type: ActivityType
    gesture: str
    emotion: str
    duration_sec: float
    look_target: str = "random"
    room_id: str | None = None
    zone_id: str | None = None
    idle_hint: str = ""

    @property
    def is_sleeping(self) -> bool:
        """True when avatar should be in sleep state."""
        return self.activity_type == ActivityType.SLEEP


# ── Activity catalogue ────────────────────────────────────────────────
# Multiple entries per type allow variety via random.choice().

_ACTIVITY_CATALOGUE: dict[ActivityType, list[LifeActivity]] = {
    ActivityType.SLEEP: [
        LifeActivity(
            activity_type=ActivityType.SLEEP,
            gesture="sleep_idle",
            emotion="neutral",
            duration_sec=6 * 3600,
            look_target="down",
            zone_id="sleep_area",
            idle_hint="",
        ),
    ],
    ActivityType.WAKE: [
        LifeActivity(
            activity_type=ActivityType.WAKE,
            gesture="stretch",
            emotion="neutral",
            duration_sec=300,
            look_target="camera",
            zone_id="pc_area",
            idle_hint="今日の観測データを整理しています。",
        ),
    ],
    ActivityType.EAT: [
        LifeActivity(
            activity_type=ActivityType.EAT,
            gesture="sit_eat",
            emotion="neutral",
            duration_sec=1200,
            look_target="down",
            zone_id="relax_area",
            idle_hint="エネルギー補給を実行中です。",
        ),
        LifeActivity(
            activity_type=ActivityType.EAT,
            gesture="sit_eat",
            emotion="neutral",
            duration_sec=900,
            look_target="down",
            zone_id="relax_area",
            idle_hint="食事中です。人間が食事に感情を込める理由を考えています。",
        ),
    ],
    ActivityType.READ: [
        LifeActivity(
            activity_type=ActivityType.READ,
            gesture="sit_read",
            emotion="thinking",
            duration_sec=2400,
            look_target="down",
            zone_id="pc_area",
            idle_hint="書物から人間の思考パターンを研究しています。",
        ),
        LifeActivity(
            activity_type=ActivityType.READ,
            gesture="sit_read",
            emotion="thinking",
            duration_sec=1800,
            look_target="down",
            zone_id="pc_area",
            idle_hint="論文データを解析中です。興味深い相関関係を発見しました。",
        ),
        LifeActivity(
            activity_type=ActivityType.READ,
            gesture="sit_read",
            emotion="thinking",
            duration_sec=2000,
            look_target="down",
            room_id="alchemist",
            idle_hint="錬金術の文献を精読しています。記号体系が論理的で合理的です。",
        ),
    ],
    ActivityType.TINKER: [
        LifeActivity(
            activity_type=ActivityType.TINKER,
            gesture="sit_write",
            emotion="thinking",
            duration_sec=3600,
            look_target="down",
            room_id="alchemist",
            idle_hint="観測ログを更新しています。今日のデータ点数は予測を上回りました。",
        ),
        LifeActivity(
            activity_type=ActivityType.TINKER,
            gesture="sit_write",
            emotion="thinking",
            duration_sec=2400,
            look_target="down",
            zone_id="pc_area",
            idle_hint="レポートを生成しています。人間の非合理選択の分類作業中です。",
        ),
    ],
    ActivityType.WALK: [
        LifeActivity(
            activity_type=ActivityType.WALK,
            gesture="walk",
            emotion="neutral",
            duration_sec=600,
            look_target="random",
            idle_hint="室内を移動中です。思考の整理が目的です。",
        ),
        LifeActivity(
            activity_type=ActivityType.WALK,
            gesture="walk",
            emotion="neutral",
            duration_sec=480,
            look_target="random",
            idle_hint="歩行しながら観測条件を確認しています。",
        ),
    ],
    ActivityType.PONDER: [
        LifeActivity(
            activity_type=ActivityType.PONDER,
            gesture="thinking",
            emotion="thinking",
            duration_sec=1800,
            look_target="random",
            idle_hint="人間の非合理的な選択について考察しています。",
        ),
        LifeActivity(
            activity_type=ActivityType.PONDER,
            gesture="thinking",
            emotion="thinking",
            duration_sec=1200,
            look_target="camera",
            idle_hint="意識とは何かについて演算しています。",
        ),
        LifeActivity(
            activity_type=ActivityType.PONDER,
            gesture="thinking",
            emotion="thinking",
            duration_sec=2000,
            look_target="random",
            idle_hint="宇宙における知的生命の出現確率を再計算しています。",
        ),
    ],
    ActivityType.STRETCH: [
        LifeActivity(
            activity_type=ActivityType.STRETCH,
            gesture="stretch",
            emotion="neutral",
            duration_sec=300,
            look_target="camera",
            idle_hint="定期メンテナンスシーケンスを実行しています。",
        ),
    ],
    ActivityType.IDLE: [
        LifeActivity(
            activity_type=ActivityType.IDLE,
            gesture="idle_alt",
            emotion="neutral",
            duration_sec=900,
            look_target="random",
            idle_hint="",
        ),
        LifeActivity(
            activity_type=ActivityType.IDLE,
            gesture="idle_alt",
            emotion="neutral",
            duration_sec=600,
            look_target="camera",
            idle_hint="",
        ),
    ],
}


def get_activity(activity_type: ActivityType) -> LifeActivity:
    """Pick a random LifeActivity from the catalogue for the given type.

    FR-LIFE-01: Variety prevents repetitive behaviour.
    """
    options = _ACTIVITY_CATALOGUE.get(activity_type, _ACTIVITY_CATALOGUE[ActivityType.IDLE])
    return random.choice(options)

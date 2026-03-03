"""Comment summarizer for burst / summary mode.

SRS refs: FR-A3-03.
バースト時にキュー内のコメントをクラスタリング・要約し、
LLM に代表コメントとして要約テキストを渡す。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from orchestrator.chat_poller import ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class CommentCluster:
    """類似コメントのクラスタ。"""

    representative: str  # クラスタ代表テキスト
    messages: list[ChatMessage] = field(default_factory=list)
    count: int = 0


def _normalize(text: str) -> str:
    """Unicode 正規化 + 空白除去 (簡易)。"""
    return re.sub(r"\s+", "", text.strip().lower())


def cluster_messages(
    messages: list[ChatMessage],
    *,
    min_cluster_size: int = 2,
) -> list[CommentCluster]:
    """コメントを簡易クラスタリング。

    同じ正規化テキストのメッセージをグループ化し、
    min_cluster_size 以上のクラスタを返す。
    残りは1つの「その他」クラスタにまとめる。
    """
    groups: dict[str, list[ChatMessage]] = {}
    for msg in messages:
        key = _normalize(msg.text)
        if key not in groups:
            groups[key] = []
        groups[key].append(msg)

    clusters: list[CommentCluster] = []
    others: list[ChatMessage] = []

    for _key, group in sorted(groups.items(), key=lambda x: -len(x[1])):
        if len(group) >= min_cluster_size:
            clusters.append(
                CommentCluster(
                    representative=group[0].text,
                    messages=group,
                    count=len(group),
                )
            )
        else:
            others.extend(group)

    # その他のコメントも1クラスタにまとめる
    if others:
        clusters.append(
            CommentCluster(
                representative=others[0].text if others else "",
                messages=others,
                count=len(others),
            )
        )

    return clusters


def build_summary_prompt(clusters: list[CommentCluster]) -> str:
    """クラスタ情報から LLM 用の要約プロンプトを構築。

    LLM はこのプロンプトをユーザーメッセージとして受け取り、
    まとめて返答する。
    """
    if not clusters:
        return "チャットが静かだね。何か面白い話でもしようか！"

    lines: list[str] = []
    lines.append("【チャット要約】以下のコメントが来ています。まとめて返答してください：")
    for i, cluster in enumerate(clusters, 1):
        if cluster.count >= 2:
            lines.append(f"  {i}. 「{cluster.representative}」(×{cluster.count}件)")
        else:
            lines.append(f"  {i}. 「{cluster.representative}」")
    return "\n".join(lines)


def summarize_for_display(clusters: list[CommentCluster]) -> str:
    """ログ/デバッグ用の要約テキスト。"""
    parts = []
    for c in clusters:
        if c.count >= 2:
            parts.append(f"「{c.representative}」×{c.count}")
        else:
            parts.append(f"「{c.representative}」")
    return " / ".join(parts) if parts else "(空)"

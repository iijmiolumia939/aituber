"""FR-A3-03: コメント要約 (summarizer) テスト。"""

from __future__ import annotations

from orchestrator.chat_poller import ChatMessage
from orchestrator.summarizer import (
    build_summary_prompt,
    cluster_messages,
    summarize_for_display,
)


def _msg(text: str, msg_id: str = "") -> ChatMessage:
    return ChatMessage(
        message_id=msg_id or f"m_{text[:8]}",
        author_channel_id="UC_test",
        author_display_name="テスト",
        text=text,
        published_at="2025-01-01T00:00:00Z",
    )


class TestClusterMessages:
    """cluster_messages のユニットテスト。"""

    def test_identical_messages_form_cluster(self) -> None:
        """同じテキストはクラスタ化される。"""
        msgs = [_msg("わこつ", f"m{i}") for i in range(5)]
        clusters = cluster_messages(msgs)
        assert len(clusters) == 1
        assert clusters[0].count == 5
        assert clusters[0].representative == "わこつ"

    def test_different_messages_no_cluster(self) -> None:
        """全て異なるテキスト → min_cluster_size 未満はその他。"""
        msgs = [_msg(f"コメント{i}", f"m{i}") for i in range(4)]
        clusters = cluster_messages(msgs, min_cluster_size=2)
        # 全て異なる → 1つの "その他" クラスタ
        assert len(clusters) == 1
        assert clusters[0].count == 4

    def test_mixed_cluster_and_others(self) -> None:
        """重複あり + ユニーク → クラスタ + その他。"""
        msgs = [
            _msg("草", "m1"),
            _msg("草", "m2"),
            _msg("草", "m3"),
            _msg("面白い", "m4"),
        ]
        clusters = cluster_messages(msgs, min_cluster_size=2)
        assert len(clusters) == 2
        # 大きいクラスタが先
        assert clusters[0].count == 3
        assert clusters[0].representative == "草"
        assert clusters[1].count == 1

    def test_empty_input(self) -> None:
        clusters = cluster_messages([])
        assert len(clusters) == 0

    def test_case_insensitive_normalization(self) -> None:
        """大文字小文字は正規化でまとめられる。"""
        msgs = [_msg("Hello", "m1"), _msg("hello", "m2"), _msg("HELLO", "m3")]
        clusters = cluster_messages(msgs, min_cluster_size=2)
        # 正規化で同一 → 1クラスタ
        assert len(clusters) == 1
        assert clusters[0].count == 3

    def test_whitespace_normalization(self) -> None:
        """空白の差異は正規化で吸収。"""
        msgs = [_msg("おはよう", "m1"), _msg("おは よう", "m2")]
        clusters = cluster_messages(msgs, min_cluster_size=2)
        assert len(clusters) == 1
        assert clusters[0].count == 2


class TestBuildSummaryPrompt:
    """build_summary_prompt のテスト。"""

    def test_with_clusters(self) -> None:
        msgs = [_msg("わこつ", f"m{i}") for i in range(5)]
        msgs.append(_msg("面白い", "m5"))
        clusters = cluster_messages(msgs, min_cluster_size=2)
        prompt = build_summary_prompt(clusters)
        assert "チャット要約" in prompt
        assert "わこつ" in prompt
        assert "×5件" in prompt

    def test_empty_returns_idle(self) -> None:
        prompt = build_summary_prompt([])
        assert "静か" in prompt

    def test_single_comment_no_count(self) -> None:
        """単一コメントクラスタは件数を表示しない。"""
        msgs = [_msg("テスト", "m1")]
        clusters = cluster_messages(msgs, min_cluster_size=2)
        prompt = build_summary_prompt(clusters)
        assert "×" not in prompt


class TestSummarizeForDisplay:
    """summarize_for_display のテスト。"""

    def test_display_format(self) -> None:
        msgs = [_msg("草", f"m{i}") for i in range(3)]
        clusters = cluster_messages(msgs)
        display = summarize_for_display(clusters)
        assert "草" in display
        assert "×3" in display

    def test_empty(self) -> None:
        assert summarize_for_display([]) == "(空)"

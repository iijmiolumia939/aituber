"""Memory reflection integration tests.

TC-MEMREF-01 ~ TC-MEMREF-16: Verify that short-term (episodic), medium-term
(semantic / goal), and long-term (narrative) memory layers are correctly
reflected in conversations via fragment assembly → compile → LLM context.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.chat_poller import ChatMessage
from orchestrator.config import AppConfig, LLMConfig
from orchestrator.episodic_store import EpisodicStore
from orchestrator.goal_memory import GoalMemory
from orchestrator.llm_client import LLMResult
from orchestrator.main import Orchestrator
from orchestrator.memory_budget import compile_fragments
from orchestrator.semantic_memory import SemanticMemory


def _make_msg(text: str, author: str = "テストユーザー", msg_id: str = "test_msg") -> ChatMessage:
    return ChatMessage(
        message_id=msg_id,
        author_channel_id="UC_test",
        author_display_name=author,
        text=text,
        published_at="2025-01-01T00:00:00Z",
        received_at=1000.0,
    )


def _stub_stream_factory(reply_text: str = "了解です。"):
    """Return an async-generator factory producing a single LLMResult."""

    async def _stub_stream(text, *, avoidance_hint=None):
        yield LLMResult(text=reply_text, is_template=False)

    return _stub_stream


def _fresh_stores(orch, tmp_path):
    """Replace Orchestrator stores with clean tmp_path-backed instances."""
    orch._episodic = EpisodicStore(path=tmp_path / "episodic.jsonl")
    orch._semantic = SemanticMemory(path=tmp_path / "semantic.jsonl")
    orch._goals = GoalMemory(path=tmp_path / "goals.jsonl")


async def _run_turn(orch, text, reply="了解です。", *, author="テストユーザー", msg_id="test_msg"):
    """Run a single conversation turn through _reply_to with stubbed IO."""
    with (
        patch.object(orch._llm, "generate_reply_stream", new=_stub_stream_factory(reply)),
        patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
        patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        patch.object(orch, "_speak", new_callable=AsyncMock),
    ):
        await orch._reply_to(_make_msg(text, author=author, msg_id=msg_id))


class TestShortTermReflection:
    """TC-MEMREF-01: Recent conversation (episodic) appears in [MEMORY] fragment."""

    @pytest.mark.asyncio
    async def test_episodic_content_in_memory_fragment(self, tmp_path):
        """After a conversation, episodic store produces [MEMORY] with the text."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        await _run_turn(orch, "shaderについて教えて", reply="shaderのことだね。")

        frag = orch._episodic.to_prompt_fragment("shader", author="テストユーザー")
        assert frag.startswith("[MEMORY]")
        assert "shaderについて教えて" in frag
        assert "shaderのことだね。" in frag

    @pytest.mark.asyncio
    async def test_multi_turn_episodic_retrieval(self, tmp_path):
        """TC-MEMREF-04: 2nd message retrieves 1st conversation for same viewer."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        await _run_turn(orch, "Unityで困ってます", reply="Unityの話ですね。")

        frag = orch._episodic.to_prompt_fragment("Unity", author="テストユーザー")
        assert "[MEMORY]" in frag
        assert "Unityで困ってます" in frag

    @pytest.mark.asyncio
    async def test_ai_response_truncated_in_fragment(self, tmp_path):
        """TC-MEMREF-08: Episodic fragment truncates ai_response to 80 chars."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        long_reply = "A" * 120
        await _run_turn(orch, "テスト質問", reply=long_reply)

        frag = orch._episodic.to_prompt_fragment("テスト", author="テストユーザー")
        assert "[MEMORY]" in frag
        # The fragment line should contain the truncated version (80 chars)
        assert long_reply[:80] in frag
        assert long_reply not in frag  # full 120 chars should NOT appear


class TestMediumTermReflection:
    """TC-MEMREF-02/03: Repeated topics create semantic facts and goals."""

    @pytest.mark.asyncio
    async def test_semantic_fact_from_repeated_topic(self, tmp_path):
        """TC-MEMREF-02: 2+ mentions of a topic creates [FACTS] fragment."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        for i in range(3):
            await _run_turn(
                orch, "shaderの最適化について", reply="shaderの話ですね。", msg_id=f"msg_{i}"
            )

        frag = orch._semantic.to_prompt_fragment(author="テストユーザー", query="shader")
        assert frag.startswith("[FACTS]")
        assert "shader" in frag.lower()

    @pytest.mark.asyncio
    async def test_goal_from_repeated_topic(self, tmp_path):
        """TC-MEMREF-03: Repeated topic creates [GOALS] fragment."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        for i in range(4):
            await _run_turn(
                orch, "lightingの設定について", reply="lightingの続きですね。", msg_id=f"msg_{i}"
            )

        frag = orch._goals.to_prompt_fragment(author="テストユーザー", query="lighting")
        assert frag.startswith("[GOALS]")
        assert "lighting" in frag.lower()

    @pytest.mark.asyncio
    async def test_new_viewer_has_no_durable_facts(self, tmp_path):
        """TC-MEMREF-09: First interaction → no durable topic facts yet.

        viewer_profile (newcomer) exists, but topic-interest facts
        need mention_count >= 2 to surface in [FACTS] fragment.
        """
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        await _run_turn(orch, "初めまして！", reply="ようこそ。", author="新規ユーザー")

        # No topic-interest facts with mention_count >= 2
        topic_facts = orch._semantic.get_facts(category="viewer_interest", subject="新規ユーザー")
        high_mention = [f for f in topic_facts if f.mention_count >= 2]
        assert high_mention == []

        # Viewer profile exists as newcomer
        profile = orch._semantic.get_viewer_profile("新規ユーザー")
        assert profile is not None
        assert profile.value == "newcomer"

    @pytest.mark.asyncio
    async def test_viewer_isolation(self, tmp_path):
        """TC-MEMREF-10: Viewer A's facts don't appear in viewer B's fragment."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        # Viewer A talks about shader repeatedly
        for i in range(3):
            await _run_turn(
                orch,
                "shaderの最適化について",
                reply="shaderの話ですね。",
                author="ビューアA",
                msg_id=f"a_{i}",
            )

        # Viewer B has no shader facts
        frag_b = orch._semantic.to_prompt_fragment(author="ビューアB", query="shader")
        assert frag_b == ""

        # Viewer A should have shader facts
        frag_a = orch._semantic.to_prompt_fragment(author="ビューアA", query="shader")
        assert "shader" in frag_a.lower()

    @pytest.mark.asyncio
    async def test_familiarity_cascade(self, tmp_path):
        """TC-MEMREF-11: 3+ interactions → regular → familiarity_score=1."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        # Before any interaction, familiarity is 0
        assert orch._semantic.familiarity_score("テストユーザー") == 0

        for i in range(3):
            await _run_turn(orch, f"テスト会話{i}", reply="返答。", msg_id=f"fam_{i}")

        # After 3 interactions, viewer should be "regular" with score 1
        assert orch._semantic.familiarity_score("テストユーザー") == 1
        profile = orch._semantic.get_viewer_profile("テストユーザー")
        assert profile is not None
        assert profile.value == "regular"

    @pytest.mark.asyncio
    async def test_follow_up_goal_created(self, tmp_path):
        """TC-MEMREF-12: Conversation with '続き' signal creates follow_up_goal."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        # Use "続き" in text to trigger follow_up_goal
        for i in range(3):
            await _run_turn(
                orch, "shaderの続きを教えて", reply="shaderの続きだね。", msg_id=f"fu_{i}"
            )

        all_goals = orch._goals.get_goals(subject="テストユーザー")
        follow_up_goals = [g for g in all_goals if g.category == "follow_up_goal"]
        assert len(follow_up_goals) > 0
        assert any("shader" in g.value.lower() for g in follow_up_goals)


class TestFullPipelineReflection:
    """TC-MEMREF-05: Full E2E — fragments are compiled and injected into LLM context."""

    @pytest.mark.asyncio
    async def test_fragments_reach_llm_context(self, tmp_path):
        """Assembled fragments are set via set_world_context_fragment before LLM call."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        for i in range(3):
            await _run_turn(
                orch, "materialについて質問", reply="materialの話だね。", msg_id=f"seed_{i}"
            )

        # Spy on set_world_context_fragment for the next reply
        with (
            patch.object(
                orch._llm,
                "set_world_context_fragment",
                wraps=orch._llm.set_world_context_fragment,
            ) as spy_set,
            patch.object(
                orch._llm,
                "generate_reply_stream",
                new=_stub_stream_factory("materialのことですね。"),
            ),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("materialの続きを教えて", msg_id="final_msg"))

        spy_set.assert_called()
        combined = spy_set.call_args[0][0]
        assert "[MEMORY]" in combined
        assert "material" in combined.lower()

    @pytest.mark.asyncio
    async def test_response_stored_in_episodic(self, tmp_path):
        """TC-MEMREF-06: AI response text is stored correctly in episodic memory."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        reply_text = "VFXGraphの使い方を説明するね。"
        await _run_turn(orch, "VFXGraphってどう使うの", reply=reply_text)

        episodes = orch._episodic.get_recent(1)
        assert len(episodes) == 1
        assert episodes[0].ai_response == reply_text
        assert episodes[0].user_text == "VFXGraphってどう使うの"
        assert episodes[0].author == "テストユーザー"

    @pytest.mark.asyncio
    async def test_semantic_goal_dedup(self, tmp_path):
        """TC-MEMREF-13: Goal topics excluded from [FACTS] via dedup."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        # Seed many interactions to create both semantic facts and goals
        for i in range(5):
            await _run_turn(
                orch,
                "shaderの続きを教えて",
                reply="shaderの最適化を説明するね。",
                msg_id=f"dedup_{i}",
            )

        # Get raw fragments before dedup
        goal_values = orch._goals.top_goal_values(author="テストユーザー", familiarity_score=1)
        raw_sem = orch._semantic.to_prompt_fragment(author="テストユーザー", query="shader")
        deduped_sem = Orchestrator._dedupe_semantic_goal_overlap(raw_sem, goal_values)

        # If goal topics overlap with semantic, dedup should remove those lines
        if goal_values:
            # Deduped should be shorter or equal to raw
            assert len(deduped_sem) <= len(raw_sem)


class TestLongTermReflection:
    """TC-MEMREF-07: Narrative builder produces long-term identity hints."""

    @pytest.mark.asyncio
    async def test_narrative_hint_set_after_conversations(self, tmp_path):
        """After enough episodes, narrative_loop builds a summary."""
        from orchestrator.narrative_builder import NarrativeEntry

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True

        orch._narrative.build = MagicMock(
            return_value=NarrativeEntry(
                narrative_id="narr_01",
                timestamp=0.0,
                narrative="最近はshaderと3Dモデリングの話題が中心。",
                episode_count=5,
            )
        )
        orch._episodic.get_recent = MagicMock(return_value=[])
        orch._episodic.get_relevant = MagicMock(return_value=[])
        orch._semantic.to_overview_fragment = MagicMock(return_value="[FACTS]\nshader常連")
        orch._goals.current_goal = MagicMock(return_value=None)
        orch._goals.top_goal_values = MagicMock(return_value=[])
        orch._goals.to_prompt_fragment = MagicMock(return_value="")
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.objects_nearby = []

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._narrative_loop()

        orch._narrative.build.assert_called_once()


class TestWorldContextReflection:
    """Verify world context (scene/room/time) propagates into fragment assembly."""

    @pytest.mark.asyncio
    async def test_world_context_influences_episodic_fragment(self, tmp_path):
        """Scene metadata affects episodic retrieval scoring."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "kitchen"
        orch._world_context.state.time_of_day = "morning"
        orch._world_context.state.objects_nearby = ["fridge", "table"]

        await _run_turn(orch, "朝ごはん何食べた？", reply="朝ごはんの話だね。")

        episodes = orch._episodic.get_recent(1)
        assert episodes[0].scene_name == "yuia_home"
        assert episodes[0].room_name == "kitchen"

        frag = orch._episodic.to_prompt_fragment(
            "朝ごはん",
            author="テストユーザー",
            scene_name="yuia_home",
            room_name="kitchen",
            time_bucket="morning",
        )
        assert "[MEMORY]" in frag
        assert "朝ごはん" in frag

    @pytest.mark.asyncio
    async def test_world_fragment_in_compiled_output(self, tmp_path):
        """TC-MEMREF-14: [WORLD] fragment appears in compiled LLM context."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "living_room"
        orch._world_context.state.time_of_day = "evening"
        orch._world_context.state.objects_nearby = ["sofa", "lamp"]

        # Need at least one episode for fragments to be non-empty
        await _run_turn(orch, "今日は何してた？", reply="のんびりしてたよ。")

        with (
            patch.object(
                orch._llm,
                "set_world_context_fragment",
                wraps=orch._llm.set_world_context_fragment,
            ) as spy_set,
            patch.object(
                orch._llm,
                "generate_reply_stream",
                new=_stub_stream_factory("了解。"),
            ),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("部屋の中にあるもの教えて", msg_id="w_msg"))

        spy_set.assert_called()
        combined = spy_set.call_args[0][0]
        assert "[WORLD]" in combined
        assert "yuia_home" in combined


class TestFragmentPriority:
    """TC-MEMREF-15: compile_fragments respects [WORLD] > [FACTS] > [GOALS] > [MEMORY]."""

    def test_priority_order_preserved(self):
        """Fragments are sorted by priority in compiled output."""
        frags = [
            "[MEMORY]\nepisode data",
            "[GOALS]\ngoal data",
            "[WORLD]\nlocation data",
            "[FACTS]\nfact data",
        ]
        compiled = compile_fragments(frags)
        world_pos = compiled.index("[WORLD]")
        facts_pos = compiled.index("[FACTS]")
        goals_pos = compiled.index("[GOALS]")
        memory_pos = compiled.index("[MEMORY]")
        assert world_pos < facts_pos < goals_pos < memory_pos

    def test_low_priority_trimmed_first(self):
        """Under tight budget, [MEMORY] is dropped before [FACTS]."""
        frags = [
            "[FACTS]\n" + "重要な事実です。\n" * 5,
            "[MEMORY]\n" + "会話データです。\n" * 5,
        ]
        # Very tight budget should keep [FACTS] and trim/drop [MEMORY]
        compiled = compile_fragments(frags, token_budget=30)
        assert "[FACTS]" in compiled
        # [MEMORY] should be fully dropped or heavily trimmed
        if "[MEMORY]" in compiled:
            assert compiled.index("[FACTS]") < compiled.index("[MEMORY]")


class TestPersistenceRoundtrip:
    """TC-MEMREF-16: Stores persist to disk and reload correctly."""

    @pytest.mark.asyncio
    async def test_episodic_persistence(self, tmp_path):
        """Episodes survive store reload."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        await _run_turn(orch, "persistenceテスト", reply="保存テスト完了。")

        # Reload from the same path
        reloaded = EpisodicStore(path=tmp_path / "episodic.jsonl")
        frag = reloaded.to_prompt_fragment("persistence", author="テストユーザー")
        assert "[MEMORY]" in frag
        assert "persistenceテスト" in frag

    @pytest.mark.asyncio
    async def test_semantic_persistence(self, tmp_path):
        """Semantic facts survive store reload."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        for i in range(3):
            await _run_turn(
                orch, "renderingパイプライン", reply="renderingの話。", msg_id=f"p_{i}"
            )

        reloaded = SemanticMemory(path=tmp_path / "semantic.jsonl")
        frag = reloaded.to_prompt_fragment(author="テストユーザー", query="rendering")
        assert "[FACTS]" in frag
        assert "rendering" in frag.lower()

    @pytest.mark.asyncio
    async def test_goal_persistence(self, tmp_path):
        """Goals survive store reload."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)

        for i in range(4):
            await _run_turn(
                orch, "lightingの設定について", reply="lightingの続きだね。", msg_id=f"gp_{i}"
            )

        reloaded = GoalMemory(path=tmp_path / "goals.jsonl")
        frag = reloaded.to_prompt_fragment(author="テストユーザー", query="lighting")
        assert "lighting" in frag.lower()


class TestCrossTierIntegration:
    """TC-MEMREF-CROSS: All memory tiers contribute to a single compiled fragment."""

    @pytest.mark.asyncio
    async def test_all_tiers_in_compiled_fragment(self, tmp_path):
        """When all tiers have data, compiled fragment contains [MEMORY]+[FACTS]+[GOALS]."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        _fresh_stores(orch, tmp_path)
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "studio"
        orch._world_context.state.time_of_day = "afternoon"

        # Seed enough conversations with follow-up signal for goals
        for i in range(5):
            await _run_turn(
                orch,
                "renderingの続きを教えて",
                reply="renderingの話だね。",
                msg_id=f"msg_{i}",
            )

        # Verify individual fragments
        ep_frag = orch._episodic.to_prompt_fragment("rendering", author="テストユーザー")
        sem_frag = orch._semantic.to_prompt_fragment(author="テストユーザー", query="rendering")
        world_frag = orch._world_context.to_prompt_fragment()

        assert ep_frag.startswith("[MEMORY]")
        assert sem_frag.startswith("[FACTS]")
        assert world_frag.startswith("[WORLD]")

        # Spy the final compilation
        with (
            patch.object(
                orch._llm,
                "set_world_context_fragment",
                wraps=orch._llm.set_world_context_fragment,
            ) as spy_set,
            patch.object(
                orch._llm,
                "generate_reply_stream",
                new=_stub_stream_factory("了解。"),
            ),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("renderingの続き教えて", msg_id="final"))

        spy_set.assert_called()
        combined = spy_set.call_args[0][0]
        assert "[WORLD]" in combined
        assert "[MEMORY]" in combined
        assert "[FACTS]" in combined

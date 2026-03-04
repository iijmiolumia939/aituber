"""Tests for orchestrator.world_context.

TC-WORLD-01 to TC-WORLD-08.
Issues: #11 E-1 Situatedness, #14 E-4 AvatarPerception
"""

from __future__ import annotations

import time

from orchestrator.world_context import WorldContext

# ── TC-WORLD-01: update() parses perception_update correctly ──────────


class TestWorldContextUpdate:
    def test_basic_fields_parsed(self):
        """TC-WORLD-01: update() extracts scene_name, room, time, objects."""
        ctx = WorldContext()
        ctx.update(
            {
                "type": "perception_update",
                "scene_name": "yuia_home",
                "room_name": "living_room",
                "time_of_day": "evening",
                "objects_nearby": ["desk", "window"],
            }
        )
        s = ctx.state
        assert s.scene_name == "yuia_home"
        assert s.room_name == "living_room"
        assert s.time_of_day == "evening"
        assert s.objects_nearby == ["desk", "window"]

    def test_avatar_appearance_parsed(self):
        """TC-WORLD-02: update() extracts avatar_appearance field."""
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home", "avatar_appearance": "casual_blue"})
        assert ctx.state.avatar_appearance == "casual_blue"

    def test_partial_message_fills_defaults(self):
        """TC-WORLD-03: Missing fields default to empty/empty-list."""
        ctx = WorldContext()
        ctx.update({"scene_name": "cafe"})
        s = ctx.state
        assert s.room_name == ""
        assert s.time_of_day == ""
        assert s.objects_nearby == []

    def test_empty_message_yields_empty_state(self):
        """TC-WORLD-04: Empty dict yields empty WorldState."""
        ctx = WorldContext()
        ctx.update({})
        assert ctx.state.scene_name == ""
        assert ctx.state.room_name == ""

    def test_repeated_update_overwrites(self):
        """TC-WORLD-04b: Multiple update() calls keep only the latest state."""
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home", "time_of_day": "morning"})
        ctx.update({"scene_name": "cafe", "time_of_day": "afternoon"})
        assert ctx.state.scene_name == "cafe"
        assert ctx.state.time_of_day == "afternoon"

    def test_updated_at_set(self):
        """TC-WORLD-05: updated_at is set to a recent monotonic timestamp."""
        before = time.monotonic()
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home"})
        after = time.monotonic()
        assert before <= ctx.state.updated_at <= after

    def test_none_values_fallback_to_empty(self):
        """TC-WORLD-06: None values in msg are treated as empty."""
        ctx = WorldContext()
        ctx.update({"scene_name": None, "room_name": None, "objects_nearby": None})
        assert ctx.state.scene_name == ""
        assert ctx.state.room_name == ""
        assert ctx.state.objects_nearby == []


# ── TC-WORLD-07: to_prompt_fragment() ────────────────────────────────


class TestToPromptFragment:
    def test_empty_scene_returns_empty_string(self):
        """TC-WORLD-07a: No scene → empty fragment."""
        ctx = WorldContext()
        assert ctx.to_prompt_fragment() == ""

    def test_scene_only(self):
        """TC-WORLD-07b: Scene name appears in output."""
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home"})
        frag = ctx.to_prompt_fragment()
        assert "[WORLD]" in frag
        assert "yuia_home" in frag

    def test_scene_and_room(self):
        """TC-WORLD-07c: scene/room format."""
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home", "room_name": "living_room"})
        frag = ctx.to_prompt_fragment()
        assert "yuia_home/living_room" in frag

    def test_time_of_day_translated(self):
        """TC-WORLD-07d: English time_of_day is translated to Japanese."""
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home", "time_of_day": "evening"})
        frag = ctx.to_prompt_fragment()
        assert "夕方" in frag

    def test_unknown_time_of_day_passthrough(self):
        """TC-WORLD-07e: Unknown time_of_day passes through as-is."""
        ctx = WorldContext()
        ctx.update({"scene_name": "cafe", "time_of_day": "dusk"})
        frag = ctx.to_prompt_fragment()
        assert "dusk" in frag

    def test_objects_nearby_listed(self):
        """TC-WORLD-08: objects_nearby appear in the fragment."""
        ctx = WorldContext()
        ctx.update(
            {
                "scene_name": "yuia_home",
                "objects_nearby": ["desk", "window", "bookshelf"],
            }
        )
        frag = ctx.to_prompt_fragment()
        assert "desk" in frag
        assert "window" in frag
        assert "bookshelf" in frag

    def test_avatar_appearance_in_fragment(self):
        """TC-WORLD-08b: avatar_appearance appears when set."""
        ctx = WorldContext()
        ctx.update({"scene_name": "yuia_home", "avatar_appearance": "casual_blue"})
        frag = ctx.to_prompt_fragment()
        assert "casual_blue" in frag

    def test_full_fragment_structure(self):
        """TC-WORLD-08c: Full fragment has expected structure."""
        ctx = WorldContext()
        ctx.update(
            {
                "scene_name": "yuia_home",
                "room_name": "living_room",
                "time_of_day": "morning",
                "objects_nearby": ["desk"],
                "avatar_appearance": "school_uniform",
            }
        )
        frag = ctx.to_prompt_fragment()
        lines = frag.splitlines()
        assert lines[0] == "[WORLD]"
        assert any("yuia_home/living_room" in line for line in lines)
        assert any("朝" in line for line in lines)
        assert any("desk" in line for line in lines)
        assert any("school_uniform" in line for line in lines)

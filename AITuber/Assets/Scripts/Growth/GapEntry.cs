// GapEntry.cs
// Data model for a single Capability Gap log entry.
// Written to JSONL by GapLogger, consumed by ReflectionRunner (M2).
//
// SRS refs: autonomous-growth.md M1

using System;
using UnityEngine;

namespace AITuber.Growth
{
    /// <summary>
    /// Represents one observed capability gap: an intent the avatar wanted to
    /// perform but could not execute because no BehaviorPolicy entry existed.
    /// Serialised as a single JSON line by GapLogger.
    /// </summary>
    [Serializable]
    public class GapEntry
    {
        /// <summary>UTC timestamp – ISO 8601: "2026-03-03T12:34:56Z"</summary>
        public string timestamp = "";

        /// <summary>Streaming-session identifier set by GapLogger.InitSession()</summary>
        public string stream_id = "";

        /// <summary>What triggered the gap: "avatar_intent_ws" | "behavior_missing"</summary>
        public string trigger = "";

        /// <summary>Current gesture/state of the avatar at the time of the gap</summary>
        public string current_state = "";

        /// <summary>What the LLM brain intended to do</summary>
        public IntendedAction intended_action;

        /// <summary>What was actually executed instead ("nod", "none", etc.)</summary>
        public string fallback_used = "";

        /// <summary>Contextual information at the time of the gap</summary>
        public GapContext context;

        /// <summary>
        /// Category of the gap – derived from intent naming convention by ActionDispatcher:
        /// "missing_motion" | "missing_behavior" | "missing_integration" | "environment_limit" | "capability_limit" | "unknown"
        /// </summary>
        public string gap_category = "";

        /// <summary>
        /// Priority score in [0, 1]. Initialised to 0; ReflectionRunner (M2) fills this in.
        /// </summary>
        public float priority_score = 0f;

        // ── Nested types ─────────────────────────────────────────────────────

        [Serializable]
        public class IntendedAction
        {
            /// <summary>"gesture" | "event" | "behavior" | "intent"</summary>
            public string type = "";

            /// <summary>Intent name sent over WebSocket (e.g. "point_at_screen")</summary>
            public string name = "";

            /// <summary>Additional parameters as a raw JSON string (may be empty)</summary>
            public string param = "";
        }

        [Serializable]
        public class GapContext
        {
            public string emotion = "";
            public string look_target = "";

            /// <summary>Most recent viewer comment, if available</summary>
            public string recent_comment = "";
        }
    }
}

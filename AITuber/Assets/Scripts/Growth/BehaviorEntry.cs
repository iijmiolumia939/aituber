// BehaviorEntry.cs
// Data model for one entry in behavior_policy.yml.
// Parsed by BehaviorPolicyLoader; consumed by ActionDispatcher.
//
// SRS refs: autonomous-growth.md M1

using UnityEngine;

namespace AITuber.Growth
{
    /// <summary>
    /// Represents a single intent-to-action mapping loaded from
    /// StreamingAssets/behavior_policy.yml.
    ///
    /// All fields use public variables to simplify the line-oriented YAML parser.
    /// </summary>
    [System.Serializable]
    public class BehaviorEntry
    {
        // ── Required ─────────────────────────────────────────────────────────

        /// <summary>
        /// The intent name used as the lookup key in BehaviorPolicyLoader.
        /// Must be non-empty; entries without an intent are skipped.
        /// </summary>
        public string intent = "";

        /// <summary>
        /// WS command to execute: "avatar_update" or "avatar_event".
        /// </summary>
        public string cmd = "";

        // ── avatar_update fields (optional) ──────────────────────────────────

        /// <summary>Gesture name forwarded to AvatarController.ApplyFromPolicy()</summary>
        public string gesture = "";

        /// <summary>Emotion name forwarded to AvatarController.ApplyFromPolicy()</summary>
        public string emotion = "";

        /// <summary>Look-target name forwarded to AvatarController.ApplyFromPolicy()</summary>
        public string look_target = "";

        // ── avatar_event fields (optional) ────────────────────────────────────

        /// <summary>Event name forwarded to AvatarController.TriggerEventFromPolicy()</summary>
        public string @event = "";

        /// <summary>Event intensity in [0, 1]</summary>
        public float intensity = 1f;

        // ── appearance_update fields (optional) FR-APPEARANCE-03 ────────────────

        /// <summary>Shader mode: "toon" | "lit". FR-SHADER-02.</summary>
        public string shader_mode = "";

        /// <summary>Costume preset ID (e.g. "casual", "formal", "pajama"). FR-APPEARANCE-01.</summary>
        public string costume = "";

        /// <summary>Hairstyle preset ID (e.g. "ponytail", "short"). FR-APPEARANCE-02.</summary>
        public string hair = "";
        // ── behavior_start fields (optional) FR-BEHAVIOR-SEQ-01 ─────────────

        /// <summary>Behavior sequence name from behaviors.json (e.g. "go_sleep"). Used when cmd="behavior_start".</summary>
        public string behavior_seq = "";
        // ── Metadata ──────────────────────────────────────────────────────────

        /// <summary>
        /// Priority when multiple entries share the same intent (higher = preferred).
        /// Reserved for future use; currently all entries are unique per intent.
        /// </summary>
        public int priority = 0;

        /// <summary>Human-readable description used in the Gap dashboard (M3)</summary>
        public string notes = "";
    }
}

// BehaviorDefinition.cs
// Data models for behaviors.json multi-step behavior sequences.
// SRS refs: FR-LIFE-01, FR-BEHAVIOR-SEQ-01
//
// Wire (behavior_start):
//   { "cmd": "behavior_start", "params": { "behavior": "go_sleep" } }
//
// Each BehaviorStep.type maps to a Coroutine handler in BehaviorSequenceRunner:
//   "face_toward"         – smoothly rotate avatar to face an InteractionSlot (Issue #48)
//   "walk_to"             – move avatar to InteractionSlot with NavMesh (collision-aware)
//   "gesture"             – fire avatar_update command (emotion + gesture + look_target)
//   "wait"                – pause for duration seconds
//   "zone_snap"           – instant teleport to nearest InteractionSlot (no animation)
//   "camera_focus_avatar" – move the active camera to an avatar-relative streaming shot

using System;
using UnityEngine;

namespace AITuber.Behavior
{
    /// <summary>
    /// A single step inside a <see cref="BehaviorSequence"/>.
    /// All fields are optional; irrelevant fields are silently ignored per step type.
    /// </summary>
    [Serializable]
    public class BehaviorStep
    {
        /// <summary>Step type: "face_toward" | "walk_to" | "gesture" | "wait" | "zone_snap" | "camera_focus_avatar"</summary>
        public string type = "";

        /// <summary>[walk_to / slot_snap] <see cref="InteractionSlot.slotId"/> of the target slot.</summary>
        public string slot_id = "";

        /// <summary>[walk_to] Lerp duration in seconds. [wait] Pause duration in seconds.</summary>
        public float duration = 0f;

        /// <summary>[gesture] Animator trigger name (e.g. "sleep_idle", "walk_stop").</summary>
        public string gesture = "";

        /// <summary>[gesture] Emotion blend-shape name (e.g. "happy", "sleepy").</summary>
        public string emotion = "";

        /// <summary>[gesture] Look target name (e.g. "camera", "down", "random").</summary>
        public string look_target = "";

        /// <summary>[camera_focus_avatar] Camera position offset in avatar local space.</summary>
        public Vector3 camera_local_offset = Vector3.zero;

        /// <summary>[camera_focus_avatar] Look-at target height above avatar root in meters.</summary>
        public float camera_target_height = 0f;

        /// <summary>[camera_focus_avatar] Override FOV. Uses the current camera FOV when <= 0.</summary>
        public float camera_fov = 0f;
    }

    /// <summary>
    /// A named sequence of <see cref="BehaviorStep"/>s loaded from behaviors.json.
    /// </summary>
    [Serializable]
    public class BehaviorSequence
    {
        /// <summary>Unique ID used in behavior_start command (e.g. "go_sleep").</summary>
        public string behavior = "";

        /// <summary>Human-readable display name (e.g. "就寝").</summary>
        public string display_name = "";

        /// <summary>Ordered steps to execute.</summary>
        public BehaviorStep[] steps = Array.Empty<BehaviorStep>();
    }

    /// <summary>
    /// Root wrapper for JsonUtility deserialization of behaviors.json.
    /// JsonUtility requires a top-level object (not array).
    /// </summary>
    [Serializable]
    internal class BehaviorDatabase
    {
        public BehaviorSequence[] behaviors = Array.Empty<BehaviorSequence>();
    }
}

// AvatarMessage.cs
// Data models for the Avatar WebSocket protocol.
// SRS refs: FR-A7-01, protocols/avatar_ws.yml, schemas/avatar_message.schema.json
//
// Uses [Serializable] + JsonUtility for zero-allocation deserialization.
// Unknown fields are silently ignored (backward compatible).

using System;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Top-level wire message: { id, ts, cmd, params }.
    /// JsonUtility ignores unknown fields automatically.
    /// Uses a wrapper approach: raw JSON parsed first, then params by cmd.
    /// </summary>
    [Serializable]
    public class AvatarMessage
    {
        public string id;
        public string ts;
        public string cmd;
    }

    /// <summary>
    /// Envelope with embedded params per command type.
    /// Python sends: { "id":"...", "ts":"...", "cmd":"avatar_update", "params":{...} }
    /// We parse the params block separately based on cmd.
    /// </summary>
    public static class AvatarMessageParser
    {
        /// <summary>
        /// Parse raw JSON into an AvatarMessage plus typed params.
        /// Returns null for invalid JSON (never throws).
        /// </summary>
        public static (AvatarMessage msg, object typedParams) Parse(string json)
        {
            AvatarMessage msg;
            try
            {
                msg = JsonUtility.FromJson<AvatarMessage>(json);
            }
            catch
            {
                return (null, null);
            }

            if (msg == null || string.IsNullOrEmpty(msg.cmd))
                return (msg, null);

            // Extract "params" sub-object for per-command parsing.
            // JsonUtility doesn't support dynamic nested objects, so we
            // look for the params wrapper.
            object typed = null;
            try
            {
                // Wrap in a per-command envelope
                switch (msg.cmd)
                {
                    case "avatar_update":
                        var upd = JsonUtility.FromJson<AvatarUpdateEnvelope>(json);
                        typed = upd?.@params;
                        break;
                    case "avatar_event":
                        var evt = JsonUtility.FromJson<AvatarEventEnvelope>(json);
                        typed = evt?.@params;
                        break;
                    case "avatar_config":
                        var cfg = JsonUtility.FromJson<AvatarConfigEnvelope>(json);
                        typed = cfg?.@params;
                        break;
                    case "avatar_reset":
                        // No params
                        break;
                    case "avatar_viseme":
                        var vis = JsonUtility.FromJson<AvatarVisemeEnvelope>(json);
                        typed = vis?.@params;
                        break;
                    case "capabilities":
                        var caps = JsonUtility.FromJson<CapabilitiesEnvelope>(json);
                        typed = caps?.@params;
                        break;
                    case "room_change":
                        var room = JsonUtility.FromJson<RoomChangeEnvelope>(json);
                        typed = room?.@params;
                        break;
                    case "zone_change":
                        var zone = JsonUtility.FromJson<ZoneChangeEnvelope>(json);
                        typed = zone?.@params;
                        break;
                    case "avatar_intent":
                        var intent = JsonUtility.FromJson<AvatarIntentEnvelope>(json);
                        typed = intent?.@params;
                        break;
                    case "appearance_update":
                        var appearance = JsonUtility.FromJson<AppearanceUpdateEnvelope>(json);
                        typed = appearance?.@params;
                        break;
                    default:
                        // Unknown command – ignore (backward compatible)
                        Debug.Log($"[AvatarWS] Unknown cmd: {msg.cmd}");
                        break;
                }
            }
            catch
            {
                // Param parse failure is non-fatal
            }

            return (msg, typed);
        }
    }

    // ── Envelope wrappers (JsonUtility needs concrete types) ─────────

    [Serializable]
    internal class AvatarUpdateEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public AvatarUpdateParams @params;
    }

    [Serializable]
    internal class AvatarEventEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public AvatarEventParams @params;
    }

    [Serializable]
    internal class AvatarConfigEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public AvatarConfigParams @params;
    }

    [Serializable]
    internal class AvatarVisemeEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public AvatarVisemeParams @params;
    }

    [Serializable]
    internal class CapabilitiesEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public CapabilitiesParams @params;
    }

    // ── avatar_update params ─────────────────────────────────────────

    [Serializable]
    public class AvatarUpdateParams
    {
        public string emotion = "neutral";
        public string gesture = "none";
        public string look_target = "camera";
        public float mouth_open = 0f;
    }

    // ── avatar_event params ──────────────────────────────────────────

    [Serializable]
    public class AvatarEventParams
    {
        public string @event = "";
        public float intensity = 1f;
    }

    // ── avatar_config params ─────────────────────────────────────────

    [Serializable]
    public class AvatarConfigParams
    {
        public float mouth_sensitivity = 1f;
        public bool blink_enabled = true;
        public string idle_motion = "default";
    }

    // ── avatar_viseme params ─────────────────────────────────────────

    [Serializable]
    public class AvatarVisemeParams
    {
        public string utterance_id = "";
        public string viseme_set = "jp_basic_8";
        public VisemeEvent[] events;
        public int crossfade_ms = 60;
        public float strength = 1f;
    }

    [Serializable]
    public class VisemeEvent
    {
        public int t_ms;
        public string v;
    }

    // ── capabilities params (optional handshake) ─────────────────

    [Serializable]
    public class CapabilitiesParams
    {
        public bool mouth_open = false;
        public bool viseme = false;
        public string[] viseme_set;
    }

    // ── room_change params ───────────────────────────────────────
    // FR-ROOM-02
    // Wire: { "cmd": "room_change", "params": { "room_id": "alchemist" } }

    [Serializable]
    public class RoomChangeParams
    {
        /// <summary>RoomDefinition.roomId と一致させる。</summary>
        public string room_id = "";
    }

    [Serializable]
    internal class RoomChangeEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public RoomChangeParams @params;
    }

    // ── zone_change params ───────────────────────────────────────
    // FR-ZONE-01
    // Wire: { "cmd": "zone_change", "params": { "zone_id": "pc_area" } }

    [Serializable]
    public class ZoneChangeParams
    {
        /// <summary>RoomDefinition.zones[].zoneId と一致させる。</summary>
        public string zone_id = "";
    }

    [Serializable]
    internal class ZoneChangeEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public ZoneChangeParams @params;
    }

    // ── avatar_intent params ─────────────────────────────────────────
    // Wire: { "cmd": "avatar_intent", "params": { "intent": "point_at_screen", "fallback": "nod" } }
    // The LLM brain sends what it *wants* to do. ActionDispatcher decides how to fulfil it.

    /// <summary>
    /// Parameters for the "avatar_intent" command.
    /// The LLM orchestrator declares a desired behaviour; ActionDispatcher resolves it
    /// against BehaviorPolicy and records a Gap if no matching entry exists.
    /// </summary>
    [Serializable]
    public class AvatarIntentParams
    {
        /// <summary>
        /// Desired intent name (e.g. "point_at_screen", "celebrate_milestone").
        /// Matched against BehaviorPolicyLoader entries.
        /// </summary>
        public string intent = "";

        /// <summary>
        /// Action to execute when no BehaviorPolicy entry matches.
        /// Use "none" or empty string to skip silently.
        /// </summary>
        public string fallback = "";

        /// <summary>Additional context as a raw JSON string (optional).</summary>
        public string context_json = "";
    }

    [Serializable]
    internal class AvatarIntentEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public AvatarIntentParams @params;
    }

    // ── appearance_update params ─────────────────────────────────────
    // FR-SHADER-02, FR-APPEARANCE-01, FR-APPEARANCE-02
    // Wire: { "cmd": "appearance_update", "params": { "shader_mode": "toon", "costume": "casual", "hair": "ponytail" } }

    /// <summary>
    /// Parameters for the "appearance_update" command.
    /// All fields are optional – omit to leave unchanged.
    /// </summary>
    [Serializable]
    public class AppearanceUpdateParams
    {
        /// <summary>"toon" | "lit"  (case-insensitive → ShaderMode enum). FR-SHADER-02.</summary>
        public string shader_mode = "";

        /// <summary>Costume preset ID (e.g. "default", "casual", "formal"). FR-APPEARANCE-01.</summary>
        public string costume = "";

        /// <summary>Hairstyle preset ID (e.g. "default", "ponytail", "short"). FR-APPEARANCE-02.</summary>
        public string hair = "";
    }

    [Serializable]
    internal class AppearanceUpdateEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public AppearanceUpdateParams @params;
    }

}

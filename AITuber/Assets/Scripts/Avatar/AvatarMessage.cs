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
                    case "avatar_intent":
                        var intent = JsonUtility.FromJson<AvatarIntentEnvelope>(json);
                        typed = intent?.@params;
                        break;
                    case "appearance_update":
                        var appearance = JsonUtility.FromJson<AppearanceUpdateEnvelope>(json);
                        typed = appearance?.@params;
                        break;
                    case "behavior_start":
                        var bstart = JsonUtility.FromJson<BehaviorStartEnvelope>(json);
                        typed = bstart?.@params;
                        break;
                    case "a2f_audio":
                        var a2fAud = JsonUtility.FromJson<A2FAudioEnvelope>(json);
                        typed = a2fAud?.@params;
                        break;
                    case "a2f_chunk":
                        var a2fChunk = JsonUtility.FromJson<A2fChunkEnvelope>(json);
                        typed = a2fChunk?.@params;
                        break;
                    case "a2f_stream_close":
                        typed = new A2fStreamCloseParams();
                        break;
                    case "a2g_chunk":
                        var a2gChunk = JsonUtility.FromJson<A2gChunkEnvelope>(json);
                        typed = a2gChunk?.@params;
                        break;
                    case "a2g_stream_close":
                        typed = new A2gStreamCloseParams();
                        break;
                    case "a2e_emotion":
                        var a2eEmo = JsonUtility.FromJson<A2EEmotionEnvelope>(json);
                        typed = a2eEmo?.@params;
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

    // ── behavior_start params ────────────────────────────────────────
    // FR-BEHAVIOR-SEQ-01
    // Wire: { "cmd": "behavior_start", "params": { "behavior": "go_sleep" } }

    /// <summary>
    /// Parameters for the "behavior_start" command.
    /// Triggers a multi-step BehaviorSequence by name in BehaviorSequenceRunner.
    /// </summary>
    [Serializable]
    public class BehaviorStartParams
    {
        /// <summary>Behavior sequence name from behaviors.json (e.g. "go_sleep").</summary>
        public string behavior = "";
    }

    [Serializable]
    internal class BehaviorStartEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public BehaviorStartParams @params;
    }

    // ── a2f_audio params ─────────────────────────────────────────────
    // Audio2Face-3D neural lip-sync audio push.
    // Wire: { "cmd": "a2f_audio", "params": {
    //   "utterance_id": "...",
    //   "pcm_b64": "<base64>",
    //   "format": "float32" | "int16",
    //   "sample_rate": 16000
    // } }

    /// <summary>Parameters for the "a2f_audio" command.</summary>
    [Serializable]
    public class A2FAudioParams
    {
        /// <summary>Optional utterance ID for debugging / dedup.</summary>
        public string utterance_id = "";

        /// <summary>Base64-encoded PCM audio bytes.</summary>
        public string pcm_b64 = "";

        /// <summary>Sample encoding: "float32" (default) or "int16".</summary>
        public string format = "float32";

        /// <summary>Sample rate in Hz (must be 16000 for A2F-3D).</summary>
        public int sample_rate = 16000;
    }

    [Serializable]
    internal class A2FAudioEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public A2FAudioParams @params;
    }

    // ── a2f_chunk params ─────────────────────────────────────────────
    // Streaming Audio2Face-3D audio push. Send chunks as TTS produces them,
    // then close the stream with a2f_stream_close.
    // Wire: { "cmd": "a2f_chunk", "params": {
    //   "pcm_b64": "<base64>",
    //   "format": "int16" | "float32",
    //   "sample_rate": 16000,
    //   "is_first": false
    // } }

    /// <summary>Parameters for the "a2f_chunk" streaming command.</summary>
    [Serializable]
    public class A2fChunkParams
    {
        /// <summary>Base64-encoded PCM audio bytes for this chunk.</summary>
        public string pcm_b64 = "";

        /// <summary>Sample encoding: "float32" (default) or "int16".</summary>
        public string format = "int16";

        /// <summary>Sample rate in Hz (must be 16000 for A2F-3D).</summary>
        public int sample_rate = 16000;

        /// <summary>True for the first chunk of a new utterance (resets plugin state).</summary>
        public bool is_first = false;
    }

    [Serializable]
    internal class A2fChunkEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public A2fChunkParams @params;
    }

    // ── a2f_stream_close params ──────────────────────────────────────
    // Signals the end of a streaming utterance (calls CloseStream on the plugin).
    // Wire: { "cmd": "a2f_stream_close", "params": {} }

    /// <summary>Parameters for the "a2f_stream_close" command. No fields required.</summary>
    [Serializable]
    public class A2fStreamCloseParams { }

    [Serializable]
    internal class A2fStreamCloseEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public A2fStreamCloseParams @params;
    }

    // ── a2g_chunk params ─────────────────────────────────────────────
    // Option A: Audio2Gesture streaming audio push. Send alongside a2f_chunk so
    // A2G generates upper-body bone rotations in sync with lip sync.
    // Wire: { "cmd": "a2g_chunk", "params": {
    //   "pcm_b64": "<base64>",
    //   "format": "int16" | "float32",
    //   "sample_rate": 16000,
    //   "is_first": false
    // } }

    /// <summary>Parameters for the "a2g_chunk" streaming command. Same schema as a2f_chunk.</summary>
    [Serializable]
    public class A2gChunkParams
    {
        public string pcm_b64    = "";
        public string format     = "int16";
        public int    sample_rate = 16000;
        public bool   is_first   = false;
    }

    [Serializable]
    internal class A2gChunkEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public A2gChunkParams @params;
    }

    // ── a2g_stream_close params ──────────────────────────────────────
    // Signals end of streaming utterance for Audio2Gesture.
    // Wire: { "cmd": "a2g_stream_close", "params": {} }

    /// <summary>Parameters for the "a2g_stream_close" command. No fields required.</summary>
    [Serializable]
    public class A2gStreamCloseParams { }

    [Serializable]
    internal class A2gStreamCloseEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public A2gStreamCloseParams @params;
    }

    // ── a2e_emotion params ───────────────────────────────────────────
    // Audio2Emotion ONNX inference result from the Python orchestrator.
    // Wire: { "cmd": "a2e_emotion", "params": { "scores": [10 floats], "label": "happy" } }
    // scores: 10-dim A2F emotion vector (indices: 1=angry, 3=disgust, 4=fear, 6=happy, 9=sad).
    // label:  dominant emotion string matching EmotionController.Apply() values.
    // SRS refs: FR-A2E-01

    /// <summary>Parameters for the "a2e_emotion" command.</summary>
    [Serializable]
    public class A2EEmotionParams
    {
        /// <summary>10-dim A2F emotion vector (float values 0..1). See FR-A2E-01.</summary>
        public float[] scores;

        /// <summary>Dominant emotion label: "neutral"|"happy"|"angry"|"sad"|"fear"|"disgust".</summary>
        public string label = "neutral";
    }

    [Serializable]
    internal class A2EEmotionEnvelope
    {
        public string id;
        public string ts;
        public string cmd;
        public A2EEmotionParams @params;
    }

}

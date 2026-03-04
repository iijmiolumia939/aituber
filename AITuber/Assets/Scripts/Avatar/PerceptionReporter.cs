// PerceptionReporter.cs
// Periodically sends perception_update messages to the Orchestrator so the
// avatar is aware of its current scene, room, time-of-day, and nearby objects.
//
// SRS refs: FR-E1-01 (Situatedness), FR-E4-01 (AvatarPerception)
// Issues: #11 E-1, #14 E-4
//
// Architecture:
//   PerceptionReporter → AvatarWSClient.SendJsonAsync → Orchestrator (Python)
//   → WorldContext.update() → LLMClient.set_world_context_fragment()

using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AITuber.Avatar
{
    /// <summary>
    /// Sends <c>perception_update</c> JSON messages to the Python Orchestrator
    /// at a configurable interval so the LLM knows the avatar's current context.
    ///
    /// FR-E1-01: scene + room + time-of-day awareness.
    /// FR-E4-01: avatar self-perception via WS push.
    /// </summary>
    public class PerceptionReporter : MonoBehaviour
    {
        // ── Inspector ────────────────────────────────────────────────

        [Header("Report interval")]
        [Tooltip("Seconds between perception_update sends.")]
        [SerializeField] private float _reportIntervalSec = 5f;

        [Header("Room / Area")]
        [Tooltip("Current room or area name within the scene (e.g. 'living_room').")]
        [SerializeField] private string _roomName = "living_room";

        [Header("Avatar appearance")]
        [Tooltip("Current outfit or appearance tag (e.g. 'casual_blue').")]
        [SerializeField] private string _avatarAppearance = "";

        [Header("Nearby objects (manual)")]
        [Tooltip("Optional hand-authored list of nearby objects; auto-detected ones are merged.")]
        [SerializeField] private List<string> _manualNearbyObjects = new();

        [Header("Auto-detect nearby objects")]
        [Tooltip("If enabled, scan for GameObjects tagged 'PerceivedObject' within _detectRadius.")]
        [SerializeField] private bool _autoDetectObjects = false;

        [SerializeField] private float _detectRadius = 3f;

        // ── Private state ────────────────────────────────────────────

        private AvatarWSClient _wsClient;
        private float _timer;

        // ── Lifecycle ────────────────────────────────────────────────

        private void Awake()
        {
            _wsClient = GetComponentInParent<AvatarWSClient>()
                        ?? FindFirstObjectByType<AvatarWSClient>();

            if (_wsClient == null)
            {
                Debug.LogWarning("[PerceptionReporter] AvatarWSClient not found; "
                                 + "perception_update will not be sent.");
            }
        }

        private void Update()
        {
            _timer += Time.deltaTime;
            if (_timer >= _reportIntervalSec)
            {
                _timer = 0f;
                SendPerceptionUpdate();
            }
        }

        // ── Core ─────────────────────────────────────────────────────

        /// <summary>
        /// Immediately send a <c>perception_update</c> message.
        /// FR-E4-01: Can also be called externally (e.g. on room change).
        /// </summary>
        public void SendPerceptionUpdate()
        {
            if (_wsClient == null || !_wsClient.IsConnected) return;

            string json = BuildJson();
            _ = _wsClient.SendJsonAsync(json);
            Debug.Log($"[PerceptionReporter] sent perception_update: {json}");
        }

        // ── Helpers ──────────────────────────────────────────────────

        private string BuildJson()
        {
            string sceneName = SceneManager.GetActiveScene().name;
            string timeOfDay = GetTimeOfDay();
            List<string> objects = GatherNearbyObjects();

            // Manual JSON assembly (no external serializer required).
            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append($"\"type\":\"perception_update\",");
            sb.Append($"\"scene_name\":{Quote(sceneName)},");
            sb.Append($"\"room_name\":{Quote(_roomName)},");
            sb.Append($"\"time_of_day\":{Quote(timeOfDay)},");
            sb.Append($"\"avatar_appearance\":{Quote(_avatarAppearance)},");

            sb.Append("\"objects_nearby\":[");
            for (int i = 0; i < objects.Count; i++)
            {
                if (i > 0) sb.Append(",");
                sb.Append(Quote(objects[i]));
            }
            sb.Append("]");
            sb.Append("}");

            return sb.ToString();
        }

        private static string GetTimeOfDay()
        {
            int hour = DateTime.Now.Hour;
            return hour switch
            {
                >= 5 and < 10 => "morning",
                >= 10 and < 17 => "afternoon",
                >= 17 and < 21 => "evening",
                _ => "night"
            };
        }

        private List<string> GatherNearbyObjects()
        {
            var result = new List<string>(_manualNearbyObjects);

            if (_autoDetectObjects)
            {
                // FR-E4-01: Detect GameObjects with tag "PerceivedObject" nearby.
                var hits = Physics.OverlapSphere(transform.position, _detectRadius);
                foreach (var col in hits)
                {
                    if (col.CompareTag("PerceivedObject"))
                    {
                        string objName = col.gameObject.name;
                        if (!result.Contains(objName))
                            result.Add(objName);
                    }
                }
            }

            return result;
        }

        private static string Quote(string s)
        {
            // Minimal JSON string quoting (ASCII-safe).
            if (s == null) return "\"\"";
            return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        }
    }
}

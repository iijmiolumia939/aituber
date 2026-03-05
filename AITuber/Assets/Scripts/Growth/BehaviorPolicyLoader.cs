// BehaviorPolicyLoader.cs
// Loads StreamingAssets/behavior_policy.yml at startup and exposes
// an intent-name → BehaviorEntry dictionary to ActionDispatcher.
//
// YAML dialect: flat list of entries separated by "- intent:" lines.
// No nested objects; unknown keys are silently skipped.
//
// SRS refs: autonomous-growth.md M1

using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AITuber.Growth
{
    /// <summary>
    /// Loads <c>StreamingAssets/behavior_policy.yml</c> on startup and provides
    /// intent-lookup to <see cref="ActionDispatcher"/>.
    ///
    /// The YAML parser is intentionally minimal (no external dependencies):
    /// it handles flat key-value pairs and list entries separated by
    /// <c>- intent:</c> lines. Nested structures are not supported.
    /// </summary>
    public class BehaviorPolicyLoader : MonoBehaviour
    {
        // ── Singleton ─────────────────────────────────────────────────────────
        public static BehaviorPolicyLoader Instance { get; private set; }

        // ── State ─────────────────────────────────────────────────────────────
        private Dictionary<string, BehaviorEntry> _policy =
            new Dictionary<string, BehaviorEntry>(StringComparer.OrdinalIgnoreCase);

        /// <summary>Read-only view of the loaded policy.</summary>
        public IReadOnlyDictionary<string, BehaviorEntry> Policy => _policy;

        // ── Unity lifecycle ───────────────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            if (Application.isPlaying) DontDestroyOnLoad(gameObject);
            Load();
        }

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>
        /// Returns the <see cref="BehaviorEntry"/> for <paramref name="intent"/>,
        /// or <c>null</c> if no entry exists. Never throws.
        /// Lookup is case-insensitive.
        /// </summary>
        public BehaviorEntry Lookup(string intent)
        {
            if (string.IsNullOrEmpty(intent)) return null;
            _policy.TryGetValue(intent, out var entry);
            return entry;
        }

        // ── Test helpers ──────────────────────────────────────────────────────

        /// <summary>
        /// Replaces the policy with a caller-supplied dictionary.
        /// Designed for unit tests; do not call in production.
        /// </summary>
        public void InjectForTest(Dictionary<string, BehaviorEntry> entries)
        {
            _policy = entries != null
                ? new Dictionary<string, BehaviorEntry>(entries, StringComparer.OrdinalIgnoreCase)
                : new Dictionary<string, BehaviorEntry>(StringComparer.OrdinalIgnoreCase);
        }

        /// <summary>Directly clear the singleton reference for test isolation.</summary>
        public static void ClearInstanceForTest() => Instance = null;

        // ── Internal ─────────────────────────────────────────────────────────

        /// <summary>Reads and parses behavior_policy.yml from StreamingAssets.</summary>
        public void Load()
        {
            _policy.Clear();

            string path = Path.Combine(Application.streamingAssetsPath, "behavior_policy.yml");
            if (!File.Exists(path))
            {
                Debug.Log("[BehaviorPolicyLoader] behavior_policy.yml not found – running with empty policy.");
                return;
            }

            try
            {
                string[] lines = File.ReadAllLines(path);
                ParseYamlLines(lines);
                Debug.Log($"[BehaviorPolicyLoader] Loaded {_policy.Count} behaviour entries.");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[BehaviorPolicyLoader] Load failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Parses a flat YAML line array into BehaviorEntry objects.
        /// Each entry starts with a "<c>- intent:</c>" line.
        /// Fields are "  key: value" pairs (leading whitespace ignored).
        /// Lines starting with '#' are treated as comments and skipped.
        /// </summary>
        public void ParseYamlLines(string[] lines)
        {
            if (lines == null) { _policy.Clear(); return; }
            _policy.Clear();

            BehaviorEntry current = null;

            foreach (string rawLine in lines)
            {
                // Trim and skip blank / comment lines
                string line = rawLine.Trim();
                if (string.IsNullOrEmpty(line) || line.StartsWith("#")) continue;

                // Inline comment removal: strip everything after " #"
                int commentIdx = line.IndexOf(" #", StringComparison.Ordinal);
                if (commentIdx > 0)
                    line = line.Substring(0, commentIdx).TrimEnd();

                // New list entry starts with "- intent:"
                if (line.StartsWith("- intent:"))
                {
                    // Commit previous entry if valid
                    CommitEntry(current);
                    current = new BehaviorEntry
                    {
                        intent = ParseValue(line, "- intent:")
                    };
                    continue;
                }

                if (current == null) continue;

                // Parse known keys
                if (line.StartsWith("cmd:"))
                    current.cmd = ParseValue(line, "cmd:");
                else if (line.StartsWith("gesture:"))
                    current.gesture = ParseValue(line, "gesture:");
                else if (line.StartsWith("emotion:"))
                    current.emotion = ParseValue(line, "emotion:");
                else if (line.StartsWith("look_target:"))
                    current.look_target = ParseValue(line, "look_target:");
                else if (line.StartsWith("event:"))
                    current.@event = ParseValue(line, "event:");
                else if (line.StartsWith("intensity:"))
                {
                    if (float.TryParse(ParseValue(line, "intensity:"),
                            System.Globalization.NumberStyles.Float,
                            System.Globalization.CultureInfo.InvariantCulture,
                            out float v))
                        current.intensity = v;
                }
                else if (line.StartsWith("priority:"))
                {
                    if (int.TryParse(ParseValue(line, "priority:"), out int p))
                        current.priority = p;
                }
                else if (line.StartsWith("notes:"))
                    current.notes = ParseValue(line, "notes:");
                else if (line.StartsWith("shader_mode:"))
                    current.shader_mode = ParseValue(line, "shader_mode:");
                else if (line.StartsWith("costume:"))
                    current.costume = ParseValue(line, "costume:");
                else if (line.StartsWith("hair:"))
                    current.hair = ParseValue(line, "hair:");
                // Unknown keys are silently ignored (forward compatible)
            }

            // Commit last entry
            CommitEntry(current);
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        private void CommitEntry(BehaviorEntry entry)
        {
            if (entry == null) return;
            if (string.IsNullOrEmpty(entry.intent))
            {
                Debug.Log("[BehaviorPolicyLoader] Skipping entry with empty intent.");
                return;
            }
            // Last-write wins for duplicate intents (same as Map.put)
            _policy[entry.intent] = entry;
        }

        private static string ParseValue(string line, string prefix)
        {
            int idx = line.IndexOf(prefix, StringComparison.OrdinalIgnoreCase);
            if (idx < 0) return "";
            return line.Substring(idx + prefix.Length).Trim().Trim('"', '\'');
        }
    }
}

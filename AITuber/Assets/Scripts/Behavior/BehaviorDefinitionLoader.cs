// BehaviorDefinitionLoader.cs
// Loads StreamingAssets/behaviors.json at startup and exposes
// a behavior-name → BehaviorSequence dictionary to BehaviorSequenceRunner.
//
// SRS refs: FR-BEHAVIOR-SEQ-01
//
// Setup: Attach to any persistent GameObject in the scene, or let
//        BehaviorSequenceRunner create it on demand.

using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AITuber.Behavior
{
    /// <summary>
    /// Singleton MonoBehaviour. Loads <c>StreamingAssets/behaviors.json</c>
    /// and provides name-keyed lookup to <see cref="BehaviorSequenceRunner"/>.
    /// </summary>
    public class BehaviorDefinitionLoader : MonoBehaviour
    {
        // ── Singleton ─────────────────────────────────────────────────────────

        public static BehaviorDefinitionLoader Instance { get; private set; }

        // ── State ─────────────────────────────────────────────────────────────

        private Dictionary<string, BehaviorSequence> _map =
            new Dictionary<string, BehaviorSequence>(StringComparer.OrdinalIgnoreCase);

        /// <summary>Read-only view of all loaded sequences.</summary>
        public IReadOnlyDictionary<string, BehaviorSequence> Behaviors => _map;

        // ── Unity lifecycle ───────────────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            if (Application.isPlaying)
                DontDestroyOnLoad(gameObject);
            Load();
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>
        /// Returns the <see cref="BehaviorSequence"/> for <paramref name="behaviorName"/>,
        /// or <c>null</c> if no entry exists. Never throws. Lookup is case-insensitive.
        /// </summary>
        public BehaviorSequence Lookup(string behaviorName)
        {
            if (string.IsNullOrEmpty(behaviorName)) return null;
            _map.TryGetValue(behaviorName, out var seq);
            return seq;
        }

        // ── Test helpers ──────────────────────────────────────────────────────

        /// <summary>
        /// Injects a test dictionary directly. Designed for unit tests only.
        /// </summary>
        public void InjectForTest(Dictionary<string, BehaviorSequence> entries)
        {
            _map = entries != null
                ? new Dictionary<string, BehaviorSequence>(entries, StringComparer.OrdinalIgnoreCase)
                : new Dictionary<string, BehaviorSequence>(StringComparer.OrdinalIgnoreCase);
        }

        /// <summary>Clears singleton reference. Call in EditMode teardown only.</summary>
        public static void ClearInstanceForTest() => Instance = null;

        // ── Internal loading ──────────────────────────────────────────────────

        private void Load()
        {
            string path = Path.Combine(Application.streamingAssetsPath, "behaviors.json");
            if (!File.Exists(path))
            {
                Debug.LogWarning($"[BehaviorLoader] {path} not found — no behaviors loaded.");
                return;
            }

            try
            {
                string json = File.ReadAllText(path);
                var db = JsonUtility.FromJson<BehaviorDatabase>(json);
                _map.Clear();
                if (db?.behaviors == null) return;

                foreach (var seq in db.behaviors)
                {
                    if (string.IsNullOrEmpty(seq.behavior)) continue;
                    _map[seq.behavior] = seq;
                }
                Debug.Log($"[BehaviorLoader] Loaded {_map.Count} behaviors: " +
                          string.Join(", ", _map.Keys));
            }
            catch (Exception ex)
            {
                Debug.LogError($"[BehaviorLoader] Failed to load behaviors.json: {ex.Message}");
            }
        }
    }
}

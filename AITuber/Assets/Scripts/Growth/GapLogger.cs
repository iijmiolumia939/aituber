// GapLogger.cs
// Appends Capability Gap entries to a per-session JSONL file.
//
// Output directory: Application.persistentDataPath/capability_gaps/
// File naming:      <stream_id>.jsonl   (e.g. stream_20260303_143000.jsonl)
//
// SRS refs: autonomous-growth.md M1

using System;
using System.IO;
using UnityEngine;

namespace AITuber.Growth
{
    /// <summary>
    /// Records <see cref="GapEntry"/> instances as newline-delimited JSON (JSONL).
    /// One file is created per streaming session; entries are appended synchronously.
    ///
    /// Access via <see cref="Instance"/> (singleton). ReflectionRunner (M2) will read
    /// the generated files after each session to compute priority scores.
    /// </summary>
    public class GapLogger : MonoBehaviour
    {
        // ── Singleton ─────────────────────────────────────────────────────────
        public static GapLogger Instance { get; private set; }

        // ── Config (Inspector) ────────────────────────────────────────────────
        [Tooltip("Stream/session identifier. Auto-generated on Awake if blank.")]
        [SerializeField] private string _streamId = "";

        [Tooltip("Disable logging without destroying the component (useful in tests).")]
        [SerializeField] private bool _enableLogging = true;

        // ── State ─────────────────────────────────────────────────────────────
        private string _logPath;
        private int    _gapCountThisSession;

        // ── Public read-only surface ──────────────────────────────────────────

        /// <summary>Number of gaps recorded during the current session.</summary>
        public int GapCountThisSession => _gapCountThisSession;

        /// <summary>Absolute path to the current JSONL log file.</summary>
        public string LogPath => _logPath;

        /// <summary>The stream identifier used for this session.</summary>
        public string StreamId => _streamId;

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
            InitSession();
        }

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>
        /// Appends a gap entry to the session log file.
        /// Automatically sets <c>stream_id</c> and <c>timestamp</c> if they are empty.
        /// Safe to call from the main thread only (synchronous file I/O).
        /// Silently no-ops on null input or when logging is disabled.
        /// </summary>
        public void Log(GapEntry entry)
        {
            if (!_enableLogging || entry == null) return;

            // Fill auto fields
            if (string.IsNullOrEmpty(entry.stream_id))
                entry.stream_id = _streamId;
            if (string.IsNullOrEmpty(entry.timestamp))
                entry.timestamp = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");

            string json;
            try
            {
                json = JsonUtility.ToJson(entry);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[GapLogger] Serialisation failed: {ex.Message}");
                return;
            }

            try
            {
                File.AppendAllText(_logPath, json + "\n");
                _gapCountThisSession++;
                Debug.Log($"[GapLogger] Gap #{_gapCountThisSession}: intent={entry.intended_action?.name} → fallback={entry.fallback_used} cat={entry.gap_category}");
            }
            catch (Exception ex)
            {
                // Logging must never crash the application
                Debug.LogWarning($"[GapLogger] File write failed: {ex.Message}");
            }
        }

        // ── Test helpers ──────────────────────────────────────────────────────

        /// <summary>Override the log path for unit tests (bypasses persistentDataPath).</summary>
        public void SetLogPathForTest(string path)
        {
            _logPath = path;
            // Ensure _streamId is initialized even when Awake's InitSession was not called
            // (e.g. singleton guard short-circuit in EditMode tests).
            if (string.IsNullOrEmpty(_streamId))
                _streamId = "stream_test_" + System.Guid.NewGuid().ToString("N");
        }

        /// <summary>Enable or disable logging (used in unit tests).</summary>
        public void SetEnabled(bool enabled) => _enableLogging = enabled;

        /// <summary>Reset session counter (used in unit tests).</summary>
        public void ResetCountForTest() => _gapCountThisSession = 0;

        /// <summary>Directly clear the singleton reference for test isolation.</summary>
        public static void ClearInstanceForTest() => Instance = null;

        // ── Internal ─────────────────────────────────────────────────────────

        private void InitSession()
        {
            if (string.IsNullOrEmpty(_streamId))
                _streamId = "stream_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss");

            string dir = Path.Combine(Application.persistentDataPath, "capability_gaps");
            try { Directory.CreateDirectory(dir); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[GapLogger] Cannot create log directory: {ex.Message}");
            }

            _logPath = Path.Combine(dir, _streamId + ".jsonl");
            _gapCountThisSession = 0;
            Debug.Log($"[GapLogger] Session started: stream_id={_streamId}  path={_logPath}");
        }
    }
}

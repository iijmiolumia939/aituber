// ActionDispatcher.cs
// Intent → Action gateway for the autonomous-growth pipeline.
//
// Receives avatar_intent commands (via AvatarController.HandleIntent),
// looks up BehaviorPolicy, executes the matching action, or falls back
// and records a Capability Gap for the ReflectionRunner.
//
// SRS refs: autonomous-growth.md M1

using UnityEngine;
using AITuber.Avatar;

namespace AITuber.Growth
{
    /// <summary>
    /// Translates <see cref="AvatarIntentParams"/> into avatar actions.
    ///
    /// Decision flow:
    /// 1. Look up <c>intent</c> in <see cref="BehaviorPolicyLoader"/>.
    /// 2. Hit  → call <see cref="AvatarController.ApplyFromPolicy"/> or
    ///           <see cref="AvatarController.TriggerEventFromPolicy"/>.
    ///    Miss → execute fallback (if any) + record <see cref="GapEntry"/>.
    ///
    /// Designed as a singleton MonoBehaviour. Wire via Inspector or place on
    /// the same GameObject as <see cref="AvatarController"/>.
    /// </summary>
    public class ActionDispatcher : MonoBehaviour
    {
        // ── Singleton ─────────────────────────────────────────────────────────
        public static ActionDispatcher Instance { get; private set; }

        // ── Dependencies ──────────────────────────────────────────────────────
        [Tooltip("AvatarController to drive. Auto-resolved from same GameObject if null.")]
        [SerializeField] private AvatarController _avatarController;

        // ── Result enum ───────────────────────────────────────────────────────

        /// <summary>Outcome of a single <see cref="Dispatch"/> call.</summary>
        public enum DispatchResult
        {
            /// <summary>BehaviorPolicy had an entry; action was executed.</summary>
            Executed,

            /// <summary>No policy entry; fallback action executed; Gap recorded.</summary>
            FallbackExecuted,

            /// <summary>No policy entry, no fallback; only Gap recorded.</summary>
            Skipped,

            /// <summary>Input was null or malformed.</summary>
            Error,
        }

        // ── Unity lifecycle ───────────────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            if (_avatarController == null)
                _avatarController = GetComponent<AvatarController>();
        }

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>
        /// Processes an <see cref="AvatarIntentParams"/> received over WebSocket.
        /// </summary>
        /// <param name="p">Intent parameters (may be null → returns Error).</param>
        /// <param name="currentState">
        /// Current avatar state label for the Gap entry (e.g. current gesture name).
        /// </param>
        /// <returns>Outcome of the dispatch attempt.</returns>
        public DispatchResult Dispatch(AvatarIntentParams p, string currentState = "unknown")
        {
            if (p == null)
            {
                Debug.LogWarning("[ActionDispatcher] Dispatch called with null params.");
                return DispatchResult.Error;
            }

            string intent   = p.intent   ?? "";
            string fallback = p.fallback ?? "";

            // ── Policy lookup ──────────────────────────────────────────────────
            var entry = BehaviorPolicyLoader.Instance != null
                ? BehaviorPolicyLoader.Instance.Lookup(intent)
                : null;

            if (entry != null)
            {
                ExecuteEntry(entry);
                Debug.Log($"[ActionDispatcher] Executed policy: intent={intent} cmd={entry.cmd}");
                return DispatchResult.Executed;
            }

            // ── Policy miss: record gap then execute fallback ──────────────────
            RecordGap(intent, fallback, currentState, p.context_json ?? "");

            if (!string.IsNullOrEmpty(fallback) && fallback != "none")
            {
                ExecuteFallback(fallback);
                Debug.Log($"[ActionDispatcher] Fallback: intent={intent} → '{fallback}'");
                return DispatchResult.FallbackExecuted;
            }

            Debug.Log($"[ActionDispatcher] Skipped: intent='{intent}' (no policy, no fallback)");
            return DispatchResult.Skipped;
        }

        // ── Internal ─────────────────────────────────────────────────────────

        private void ExecuteEntry(BehaviorEntry entry)
        {
            if (_avatarController == null) return;

            switch (entry.cmd)
            {
                case "avatar_update":
                    _avatarController.ApplyFromPolicy(entry.emotion, entry.gesture, entry.look_target);
                    break;
                case "avatar_event":
                    _avatarController.TriggerEventFromPolicy(entry.@event, entry.intensity);
                    break;
                default:
                    Debug.LogWarning($"[ActionDispatcher] Unknown cmd in policy entry: '{entry.cmd}'");
                    break;
            }
        }

        private void ExecuteFallback(string fallback)
        {
            if (_avatarController == null) return;
            // Fallback is interpreted as a gesture name (most general fallback)
            _avatarController.ApplyFromPolicy(null, fallback, null);
        }

        private void RecordGap(
            string intent, string fallback, string currentState, string contextJson)
        {
            var logger = GapLogger.Instance;
            if (logger == null) return;

            string emotionCtx     = _avatarController != null ? _avatarController.CurrentEmotion    : "";
            string lookTargetCtx  = _avatarController != null ? _avatarController.CurrentLookTarget : "";

            var gap = new GapEntry
            {
                current_state = currentState,
                trigger       = "avatar_intent_ws",
                fallback_used = string.IsNullOrEmpty(fallback) ? "none" : fallback,
                gap_category  = CategorizeGap(intent),
                intended_action = new GapEntry.IntendedAction
                {
                    type  = "intent",
                    name  = intent,
                    param = contextJson,
                },
                context = new GapEntry.GapContext
                {
                    emotion       = emotionCtx,
                    look_target   = lookTargetCtx,
                    recent_comment = "",
                },
            };

            logger.Log(gap);
        }

        /// <summary>
        /// Infers a gap category from the intent name's prefix convention.
        /// This provides a rough classification for the ReflectionRunner without
        /// any additional LLM call at recording time.
        /// </summary>
        public static string CategorizeGap(string intent)
        {
            if (string.IsNullOrEmpty(intent))      return "unknown";
            if (intent.StartsWith("gesture_"))     return "missing_motion";
            if (intent.StartsWith("emote_"))       return "missing_motion";
            if (intent.StartsWith("event_"))       return "missing_behavior";
            if (intent.StartsWith("integrate_"))   return "missing_integration";
            if (intent.StartsWith("env_"))         return "environment_limit";
            return "capability_limit";
        }
    }
}

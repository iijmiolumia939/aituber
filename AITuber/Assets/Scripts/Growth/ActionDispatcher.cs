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
    /// <summary>Outcome of a single <see cref="ActionDispatcher.Dispatch"/> call.</summary>
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

        // ── Events ────────────────────────────────────────────────────────────
        /// <summary>Fired after each Dispatch call with the result.</summary>
        public event System.Action<DispatchResult> OnDispatched;

        // ── Dependencies ──────────────────────────────────────────────────────
        [Tooltip("AvatarController to drive. Auto-resolved from same GameObject if null.")]
        [SerializeField] private AvatarController _avatarController;

        // Cached co-located component references (resolved in Awake via GetComponent).
        // Using direct references avoids relying on the global singleton at call time,
        // which is fragile in EditMode unit tests where singletons may be cleared.
        private GapLogger            _gapLogger;
        private BehaviorPolicyLoader _policyLoader;

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

            if (_avatarController == null)
                _avatarController = GetComponent<AvatarController>();

            // Prefer co-located components; fall back to singletons at dispatch time.
            _gapLogger    = GetComponent<GapLogger>();
            _policyLoader = GetComponent<BehaviorPolicyLoader>();
        }

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        // ── Test helpers ──────────────────────────────────────────────────────

        /// <summary>Directly clear the singleton reference for test isolation.</summary>
        public static void ClearInstanceForTest() => Instance = null;

        /// <summary>Override the GapLogger reference for tests (bypasses singleton).</summary>
        public void SetGapLoggerForTest(GapLogger logger) => _gapLogger = logger;

        /// <summary>Override the BehaviorPolicyLoader reference for tests (bypasses singleton).</summary>
        public void SetPolicyLoaderForTest(BehaviorPolicyLoader loader) => _policyLoader = loader;

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
            DispatchResult result;

            if (p == null)
            {
                Debug.LogWarning("[ActionDispatcher] Dispatch called with null params.");
                result = DispatchResult.Error;
                OnDispatched?.Invoke(result);
                return result;
            }

            string intent   = p.intent   ?? "";
            string fallback = p.fallback ?? "";

            // ── Policy lookup ──────────────────────────────────────────────────
            var bpl = _policyLoader != null ? _policyLoader : BehaviorPolicyLoader.Instance;
            var entry = bpl != null ? bpl.Lookup(intent) : null;

            if (entry != null)
            {
                ExecuteEntry(entry);
                Debug.Log($"[ActionDispatcher] Executed policy: intent={intent} cmd={entry.cmd}");
                result = DispatchResult.Executed;
                OnDispatched?.Invoke(result);
                return result;
            }

            // ── Policy miss: record gap then execute fallback ──────────────────
            RecordGap(intent, fallback, currentState, p.context_json ?? "");

            if (!string.IsNullOrEmpty(fallback) && fallback != "none")
            {
                ExecuteFallback(fallback);
                Debug.Log($"[ActionDispatcher] Fallback: intent={intent} → '{fallback}'");
                result = DispatchResult.FallbackExecuted;
                OnDispatched?.Invoke(result);
                return result;
            }

            Debug.Log($"[ActionDispatcher] Skipped: intent='{intent}' (no policy, no fallback)");
            result = DispatchResult.Skipped;
            OnDispatched?.Invoke(result);
            return result;
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
                case "appearance_update":
                    // FR-APPEARANCE-03: Autonomous appearance change via BehaviorPolicy
                    var appearCtrl = AppearanceController.Instance;
                    if (appearCtrl != null)
                    {
                        if (!string.IsNullOrEmpty(entry.shader_mode))
                        {
                            if (System.Enum.TryParse<ShaderMode>(entry.shader_mode, true, out var mode))
                                appearCtrl.ApplyShaderMode(mode);
                        }
                        if (!string.IsNullOrEmpty(entry.costume)) appearCtrl.ApplyCostume(entry.costume);
                        if (!string.IsNullOrEmpty(entry.hair))    appearCtrl.ApplyHair(entry.hair);
                    }
                    break;
                case "behavior_start":
                    // FR-BEHAVIOR-SEQ-01: Trigger multi-step behavior sequence
                    var runner = AITuber.Behavior.BehaviorSequenceRunner.Instance;
                    if (runner != null && !string.IsNullOrEmpty(entry.behavior_seq))
                        runner.StartBehavior(entry.behavior_seq);
                    else
                        Debug.LogWarning($"[ActionDispatcher] behavior_start: runner={runner != null} seq='{entry.behavior_seq}'");
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
            var logger = _gapLogger != null ? _gapLogger : GapLogger.Instance;
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
            if (intent.StartsWith("integrate_"))        return "missing_integration";
            if (intent.StartsWith("env_"))               return "environment_limit";
            if (intent.StartsWith("change_appearance_")) return "missing_appearance";
            return "capability_limit";
        }
    }
}

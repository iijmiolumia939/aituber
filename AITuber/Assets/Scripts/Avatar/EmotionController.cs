// EmotionController.cs
// Manages emotion blend-shape transitions and auto-blink for the avatar face mesh.
// Extracted from AvatarController as part of the Strangler Fig refactor (Issue #52, Phase 2).
//
// SRS refs: FR-EMOTION-01, FR-A7-01

using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Drives emotion BlendShape transitions and auto-blink.
    /// Attach to the same GameObject as AvatarController.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class EmotionController : MonoBehaviour
    {
        // ── Inspector ──────────────────────────────────────────────────────────

        [Header("Face Mesh")]
        [SerializeField] private SkinnedMeshRenderer _faceMesh;

        [Header("Emotion BlendShape Indices")]
        [Tooltip("BlendShape index for joy/happy expression")]
        [SerializeField] private int _joyBlendIndex       = -1;
        [Tooltip("BlendShape index for angry expression")]
        [SerializeField] private int _angryBlendIndex     = -1;
        [Tooltip("BlendShape index for sorrow/sad expression")]
        [SerializeField] private int _sorrowBlendIndex    = -1;
        [Tooltip("BlendShape index for surprised expression")]
        [SerializeField] private int _surprisedBlendIndex = -1;
        [Tooltip("BlendShape index for thinking expression")]
        [SerializeField] private int _thinkingBlendIndex  = -1;

        [Header("Blink Settings")]
        [Tooltip("BlendShape index for eye close / blink (Fcl_EYE_Close)")]
        [SerializeField] private int   _blinkBlendIndex  = -1;
        [SerializeField] private float _blinkIntervalMin = 2.5f;
        [SerializeField] private float _blinkIntervalMax = 6.0f;
        [SerializeField] private float _blinkDuration    = 0.12f;

        // ── Saved defaults (cached from SerializedFields in OnEnable) ──────────

        private float _defaultBlinkIntervalMin;
        private float _defaultBlinkIntervalMax;
        private float _defaultBlinkDuration;

        // ── Emotion blend state ────────────────────────────────────────────────

        private float _targetEmotionWeight;
        private float _currentEmotionWeight;
        private int   _activeEmotionBlendIndex = -1;
        private const float EmotionSmoothSpeed = 8f;

        // ── Blink state ────────────────────────────────────────────────────────

        private bool  _blinkEnabled = true;
        private float _nextBlinkTime;
        private float _blinkPhase;   // 0=idle, >0=blink in progress
        private bool  _isBlinking;

        // ── Unity lifecycle ────────────────────────────────────────────────────

        private void OnEnable()
        {
            // Cache Inspector defaults so emotion-linked changes can restore them.
            _defaultBlinkIntervalMin = _blinkIntervalMin;
            _defaultBlinkIntervalMax = _blinkIntervalMax;
            _defaultBlinkDuration    = _blinkDuration;
            ScheduleNextBlink();
        }

        private void Update()
        {
            UpdateEmotionBlend();
            if (_blinkEnabled) UpdateBlink();
        }

        // ── Public API ─────────────────────────────────────────────────────────

        /// <summary>Applies an emotion string: sets blend-shape target and adjusts blink behaviour.</summary>
        public void Apply(string emotion)
        {
            // Reset previous emotion blend shape to zero.
            if (_activeEmotionBlendIndex >= 0 && _faceMesh != null)
                _faceMesh.SetBlendShapeWeight(_activeEmotionBlendIndex, 0f);

            _activeEmotionBlendIndex = emotion switch
            {
                "happy"                => _joyBlendIndex,
                "angry"                => _angryBlendIndex,
                "sad"                  => _sorrowBlendIndex,
                "surprised" or "panic" => _surprisedBlendIndex,
                "thinking"             => _thinkingBlendIndex,
                _                      => -1, // neutral: no emotion blend
            };

            _targetEmotionWeight = (_activeEmotionBlendIndex >= 0) ? 100f : 0f;

            // Emotion-linked blink behaviour.
            switch (emotion)
            {
                case "surprised":
                case "panic":
                    // Wide-eyed stare: pause blinking for ~5 seconds.
                    _isBlinking    = false;
                    _blinkDuration = _defaultBlinkDuration;
                    _nextBlinkTime = Time.time + 5f;
                    break;
                case "happy":
                    // Lively: tighter blink interval.
                    _blinkIntervalMin = Mathf.Min(_defaultBlinkIntervalMin, 1.5f);
                    _blinkIntervalMax = Mathf.Min(_defaultBlinkIntervalMax, 3.0f);
                    _blinkDuration    = _defaultBlinkDuration;
                    break;
                case "sad":
                    // Heavy lids: slower, longer blinks.
                    _blinkIntervalMin = 4.0f;
                    _blinkIntervalMax = 8.0f;
                    _blinkDuration    = 0.20f;
                    break;
                default:
                    // Restore Inspector defaults.
                    _blinkIntervalMin = _defaultBlinkIntervalMin;
                    _blinkIntervalMax = _defaultBlinkIntervalMax;
                    _blinkDuration    = _defaultBlinkDuration;
                    break;
            }

            LastAppliedEmotionForTest = emotion;
        }

        /// <summary>Enables or disables auto-blink (forwarded from avatar_config).</summary>
        public void SetBlinkEnabled(bool enabled) => _blinkEnabled = enabled;

        /// <summary>
        /// Applies emotion from an Audio2Emotion 10-dim A2F vector (FR-A2E-01).
        /// Reads the dominant non-neutral slot, maps to an emotion string, and calls Apply().
        ///
        /// A2F 10-dim slot assignment:
        ///   1=angry, 3=disgust, 4=fear, 6=happy, 9=sad (all others ≈ neutral).
        /// A2E confidence threshold: 0.05 — below that, keep current emotion unchanged.
        /// </summary>
        public void ApplyA2E(float[] scores10)
        {
            if (scores10 == null || scores10.Length < 10) return;

            // Find the highest-scoring non-neutral A2F slot.
            int   bestSlot = -1;
            float bestVal  = 0.05f;  // minimum confidence threshold
            int[] activeSlots = { 1, 3, 4, 6, 9 };
            foreach (int slot in activeSlots)
            {
                if (scores10[slot] > bestVal)
                {
                    bestVal  = scores10[slot];
                    bestSlot = slot;
                }
            }

            string emotion = bestSlot switch
            {
                1 => "angry",
                3 => "thinking",     // disgust → thinking (closest available)
                4 => "panic",        // fear    → panic
                6 => "happy",
                9 => "sad",
                _ => "neutral",
            };

            Apply(emotion);
        }

        // ── Private methods ────────────────────────────────────────────────────

        private void UpdateEmotionBlend()
        {
            // Smooth emotion transitions.
            _currentEmotionWeight = Mathf.Lerp(
                _currentEmotionWeight, _targetEmotionWeight,
                Time.deltaTime * EmotionSmoothSpeed);

            if (_faceMesh != null && _activeEmotionBlendIndex >= 0)
            {
                _faceMesh.SetBlendShapeWeight(
                    _activeEmotionBlendIndex,
                    Mathf.Clamp(_currentEmotionWeight, 0f, 100f));
            }
        }

        private void ScheduleNextBlink()
        {
            _nextBlinkTime = Time.time + UnityEngine.Random.Range(_blinkIntervalMin, _blinkIntervalMax);
            _isBlinking    = false;
            _blinkPhase    = 0f;
        }

        private void UpdateBlink()
        {
            if (_faceMesh == null || _blinkBlendIndex < 0) return;

            if (!_isBlinking)
            {
                if (Time.time >= _nextBlinkTime)
                {
                    _isBlinking = true;
                    _blinkPhase = 0f;
                }
                return;
            }

            _blinkPhase += Time.deltaTime;
            float half = _blinkDuration * 0.5f;

            float weight;
            if (_blinkPhase < half)
            {
                // Closing
                weight = Mathf.Lerp(0f, 100f, _blinkPhase / half);
            }
            else if (_blinkPhase < _blinkDuration)
            {
                // Opening
                weight = Mathf.Lerp(100f, 0f, (_blinkPhase - half) / half);
            }
            else
            {
                // Done
                weight = 0f;
                ScheduleNextBlink();
            }

            _faceMesh.SetBlendShapeWeight(_blinkBlendIndex, weight);
        }

        // ── Test seams ─────────────────────────────────────────────────────────

        /// <summary>Records the most recent emotion passed to Apply(). For tests only.</summary>
        public string LastAppliedEmotionForTest { get; private set; }

        /// <summary>Exposes blink active state. For tests only.</summary>
        public bool IsBlinkingForTest => _isBlinking;

        /// <summary>Exposes next scheduled blink time. For tests only.</summary>
        public float NextBlinkTimeForTest => _nextBlinkTime;

        /// <summary>Exposes current blink interval min. For tests only.</summary>
        public float BlinkIntervalMinForTest => _blinkIntervalMin;

        /// <summary>Exposes current blink interval max. For tests only.</summary>
        public float BlinkIntervalMaxForTest => _blinkIntervalMax;

        /// <summary>Exposes current blink duration. For tests only.</summary>
        public float BlinkDurationForTest => _blinkDuration;

        /// <summary>Injects a face mesh reference. For tests only.</summary>
        public void SetFaceMeshForTest(SkinnedMeshRenderer mesh) => _faceMesh = mesh;

        /// <summary>Injects blend indices and blink parameters. For tests only.</summary>
        public void SetIndicesForTest(int joy, int angry, int sorrow, int surprised, int thinking, int blink)
        {
            _joyBlendIndex       = joy;
            _angryBlendIndex     = angry;
            _sorrowBlendIndex    = sorrow;
            _surprisedBlendIndex = surprised;
            _thinkingBlendIndex  = thinking;
            _blinkBlendIndex     = blink;
        }
    }
}

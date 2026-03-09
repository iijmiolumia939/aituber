// LipSyncController.cs
// LipSync (3-mode: RMS mouth_open / phoneme viseme / Audio2Face neural) + ARKit PerfectSync.
// Extracted from AvatarController.cs (Issue #52, Phase 4 – Strangler Fig).
//
// SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02
// M21: LipSyncMode enum added to eliminate dual-write race condition (Issue #56).

using System;
using System.Collections.Generic;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Selects which system drives mouth blendshapes each frame.
    /// Eliminates the dual-write race condition when both A2F and TTS visemes
    /// are active simultaneously. (M21 / Issue #56)
    /// </summary>
    public enum LipSyncMode
    {
        /// <summary>A2F neural blendshapes only. TTS viseme writes are suppressed.</summary>
        A2FNeural,
        /// <summary>TTS phoneme visemes only. A2F ApplyToMesh is suppressed.</summary>
        TtsViseme,
        /// <summary>A2F takes precedence while IsSpeaking; viseme drives otherwise. (default)</summary>
        Hybrid,
    }

    [DisallowMultipleComponent]
    public sealed class LipSyncController : MonoBehaviour
    {
        // ── SerializedFields ─────────────────────────────────────────

        [Header("BlendShape References")]
        [Tooltip("Face SkinnedMeshRenderer. Auto-propagated by AvatarController if not set here.")]
        [SerializeField] private SkinnedMeshRenderer _faceMesh;

        [Header("Blend Shape Indices (set in Inspector)")]
        [Tooltip("BlendShape index for mouth open (ParamMouthOpenY)")]
        [SerializeField] private int _mouthOpenBlendIndex = -1;

        [Header("Viseme BlendShape Indices (jp_basic_8)")]
        [Tooltip("BlendShape index for vowel A (Fcl_MTH_A)")]
        [SerializeField] private int _visemeAIndex = -1;
        [Tooltip("BlendShape index for vowel I (Fcl_MTH_I)")]
        [SerializeField] private int _visemeIIndex = -1;
        [Tooltip("BlendShape index for vowel U (Fcl_MTH_U)")]
        [SerializeField] private int _visemeUIndex = -1;
        [Tooltip("BlendShape index for vowel E (Fcl_MTH_E)")]
        [SerializeField] private int _visemeEIndex = -1;
        [Tooltip("BlendShape index for vowel O (Fcl_MTH_O)")]
        [SerializeField] private int _visemeOIndex = -1;

        [Header("ARKit PerfectSync Indices \u2013 Mouth")]
        [Tooltip("jawOpen [78]")]
        [SerializeField] private int _jawOpenIndex         = -1;
        [Tooltip("mouthFunnel [82]")]
        [SerializeField] private int _mouthFunnelIndex     = -1;
        [Tooltip("mouthPucker [83]")]
        [SerializeField] private int _mouthPuckerIndex     = -1;
        [Tooltip("mouthLeft [84]")]
        [SerializeField] private int _mouthLeftIndex       = -1;
        [Tooltip("mouthRight [85]")]
        [SerializeField] private int _mouthRightIndex      = -1;
        [Tooltip("mouthRollUpper [86]")]
        [SerializeField] private int _mouthRollUpperIndex  = -1;
        [Tooltip("mouthRollLower [87]")]
        [SerializeField] private int _mouthRollLowerIndex  = -1;
        [Tooltip("mouthShrugUpper [88]")]
        [SerializeField] private int _mouthShrugUpperIndex = -1;
        [Tooltip("mouthShrugLower [89]")]
        [SerializeField] private int _mouthShrugLowerIndex = -1;
        [Tooltip("mouthClose [90]")]
        [SerializeField] private int _mouthCloseIndex      = -1;
        [Tooltip("mouthSmile_L [91]")]
        [SerializeField] private int _mouthSmileLIndex     = -1;
        [Tooltip("mouthSmile_R [92]")]
        [SerializeField] private int _mouthSmileRIndex     = -1;
        [Tooltip("mouthFrown_L [93]")]
        [SerializeField] private int _mouthFrownLIndex     = -1;
        [Tooltip("mouthFrown_R [94]")]
        [SerializeField] private int _mouthFrownRIndex     = -1;
        [Tooltip("mouthLowerDown_L [99]")]
        [SerializeField] private int _mouthLowerDownLIndex = -1;
        [Tooltip("mouthLowerDown_R [100]")]
        [SerializeField] private int _mouthLowerDownRIndex = -1;
        [Tooltip("mouthStretch_L [103]")]
        [SerializeField] private int _mouthStretchLIndex   = -1;
        [Tooltip("mouthStretch_R [104]")]
        [SerializeField] private int _mouthStretchRIndex   = -1;

        [Header("ARKit Lip Sync \u2013 Global Articulation Strength")]
        [Range(0f, 1f), Tooltip("Master strength for ARKit-driven phoneme shapes. 0=off\u3001 1=full. Tune here instead of editing profiles.")]
        [SerializeField] private float _articulationStrength = 0.85f;

        [Header("LipSync Mode (M21)")]
        [Tooltip("A2FNeural: only A2F drives mouth (TTS viseme suppressed). [default, best quality with A2F v3.0+]\n"
               + "TtsViseme: only TTS phoneme viseme drives mouth (A2F muted).\n"
               + "Hybrid: A2F has precedence while IsSpeaking; viseme drives otherwise.")]
        [SerializeField] private LipSyncMode _lipSyncMode = LipSyncMode.A2FNeural;

        [Header("Audio2Face Neural Lip Sync (optional)")]
        [Tooltip("Optional Audio2FaceLipSync component for neural blendshape generation. "
               + "When set and active, a2f_audio WS commands bypass the phoneme-based lip sync.")]
        [SerializeField] private Audio2FaceLipSync _a2fLipSync;

        // ── Mouth open state (FR-LIPSYNC-01) ─────────────────────────

        private float _targetMouthOpen;
        private float _currentMouthOpen;
        private const float MouthSmoothSpeed = 20f;
        private float _mouthSensitivity = 1f;

        // ── Viseme state (FR-LIPSYNC-02) ─────────────────────────────

        private VisemeEvent[] _visemeEvents;
        private int _visemeIndex;
        private float _visemeStartTime;
        private bool _visemePlaying;
        private float _visemeCrossfadeMs = 60f;
        private float _visemeStrength = 1f;

        // Anticipation: mouth starts moving this many ms BEFORE the phoneme onset.
        private const float VisemeAnticipationMs = 50f;

        // Coarticulation: start blending toward the NEXT viseme when this fraction
        // through the current phoneme (60% = last 40% of the phoneme overlaps with next).
        private const float CoarticulationStart = 0.60f;

        // Per-vowel blend shape current weights (for crossfade)
        private float _currentVisemeA;
        private float _currentVisemeI;
        private float _currentVisemeU;
        private float _currentVisemeE;
        private float _currentVisemeO;

        // ── ARKit PerfectSync current weights (per-shape lerp state, no allocations) ──

        private float _curJawOpen;
        private float _curMouthFunnel, _curMouthPucker;
        private float _curMouthLeft, _curMouthRight;
        private float _curMouthRollUpper, _curMouthRollLower;
        private float _curMouthShrugUpper, _curMouthShrugLower;
        private float _curMouthClose;
        private float _curMouthSmileL, _curMouthSmileR;
        private float _curMouthFrownL, _curMouthFrownR;
        private float _curMouthLowerDownL, _curMouthLowerDownR;
        private float _curMouthStretchL, _curMouthStretchR;

        // ── ARKit PerfectSync \u2013 Phoneme profiles ──────────────────────────────

        private struct ARKitWeights
        {
            public float jawOpen;
            public float mouthFunnel, mouthPucker;
            public float mouthLeft, mouthRight;
            public float mouthRollUpper, mouthRollLower;
            public float mouthShrugUpper, mouthShrugLower;
            public float mouthClose;
            public float mouthSmileL, mouthSmileR;
            public float mouthFrownL, mouthFrownR;
            public float mouthLowerDownL, mouthLowerDownR;
            public float mouthStretchL, mouthStretchR;
        }

        // jp_basic_8 \u2192 ARKit phoneme profiles. Values are normalised 0..1.
        // Tuned for QuQu avatar (jawOpen=#78 etc.). Adjust _articulationStrength
        // in the Inspector to scale all shapes globally without editing these.
        private static readonly Dictionary<string, ARKitWeights> s_ArkitProfiles =
            new Dictionary<string, ARKitWeights>
            {
                ["sil"] = new ARKitWeights { mouthClose = 0.15f },
                ["m"]   = new ARKitWeights { mouthClose = 0.60f, mouthPucker = 0.15f },
                ["fv"]  = new ARKitWeights { jawOpen = 0.10f, mouthFunnel = 0.20f, mouthRollLower = 0.25f },
                // \u3042: jaw fully drops, lower lip descends
                ["a"]   = new ARKitWeights
                {
                    jawOpen = 0.70f,
                    mouthLowerDownL = 0.50f, mouthLowerDownR = 0.50f,
                    mouthShrugLower = 0.15f,
                    mouthLeft = 0.05f, mouthRight = 0.05f,
                },
                // \u3044: wide retracted corners (smile shape), narrow opening
                ["i"]   = new ARKitWeights
                {
                    jawOpen = 0.25f,
                    mouthSmileL = 0.60f, mouthSmileR = 0.60f,
                    mouthStretchL = 0.30f, mouthStretchR = 0.30f,
                    mouthLowerDownL = 0.15f, mouthLowerDownR = 0.15f,
                },
                // \u3046: rounded/puckered
                ["u"]   = new ARKitWeights
                {
                    jawOpen = 0.20f,
                    mouthFunnel = 0.65f,
                    mouthPucker = 0.50f,
                    mouthRollLower = 0.20f,
                },
                // \u3048: medium open, slight smile
                ["e"]   = new ARKitWeights
                {
                    jawOpen = 0.40f,
                    mouthSmileL = 0.25f, mouthSmileR = 0.25f,
                    mouthLowerDownL = 0.25f, mouthLowerDownR = 0.25f,
                    mouthLeft = 0.10f, mouthRight = 0.10f,
                },
                // \u304a: rounded open mouth
                ["o"]   = new ARKitWeights
                {
                    jawOpen = 0.55f,
                    mouthFunnel = 0.40f,
                    mouthPucker = 0.25f,
                    mouthLowerDownL = 0.30f, mouthLowerDownR = 0.30f,
                    mouthRollLower = 0.15f,
                    mouthLeft = 0.05f, mouthRight = 0.05f,
                },
            };

        // ── Lifecycle ─────────────────────────────────────────────────

        private void Awake()
        {
            if (_a2fLipSync == null)
                _a2fLipSync = GetComponent<Audio2FaceLipSync>();
        }

        // ── Initialization ────────────────────────────────────────────

        /// <summary>
        /// Called from AvatarController.Start() after face mesh auto-detection.
        /// Propagates the detected mesh if this component's own _faceMesh is not wired in Inspector.
        /// Also triggers ARKit auto-detection and wires Audio2FaceLipSync index maps.
        /// </summary>
        public void Initialize(SkinnedMeshRenderer faceMesh)
        {
            if (_faceMesh == null && faceMesh != null)
            {
                _faceMesh = faceMesh;
                Debug.Log($"[LipSync] _faceMesh propagated: {_faceMesh.name}");
            }

            if (_faceMesh != null && _faceMesh.sharedMesh != null && _jawOpenIndex < 0)
                AutoDetectArkitIndices();

            if (_a2fLipSync != null)
            {
                _a2fLipSync.SetIndexMap(
                    _jawOpenIndex,
                    _mouthFunnelIndex,  _mouthPuckerIndex,
                    _mouthLeftIndex,    _mouthRightIndex,
                    _mouthRollUpperIndex, _mouthRollLowerIndex,
                    _mouthShrugUpperIndex, _mouthShrugLowerIndex,
                    _mouthCloseIndex,
                    _mouthSmileLIndex,  _mouthSmileRIndex,
                    _mouthFrownLIndex,  _mouthFrownRIndex,
                    _mouthLowerDownLIndex, _mouthLowerDownRIndex,
                    _mouthStretchLIndex, _mouthStretchRIndex);
                _a2fLipSync.SetVowelMap(
                    _visemeAIndex, _visemeIIndex, _visemeUIndex,
                    _visemeEIndex, _visemeOIndex);
                Debug.Log($"[LipSync] Audio2FaceLipSync index map wired. jawOpen={_jawOpenIndex}");
            }
        }

        // ── Config ─────────────────────────────────────────────────────

        /// <summary>Switch lip sync drive mode at runtime (M21 / Issue #56).</summary>
        public void SetLipSyncMode(LipSyncMode mode) => _lipSyncMode = mode;

        public void SetMouthSensitivity(float v) => _mouthSensitivity = v;

        /// <summary>Set mouth open target from avatar_update mouth_open (FR-LIPSYNC-01).</summary>
        public void SetMouthOpen(float v) => _targetMouthOpen = Mathf.Clamp01(v);

        // ── Unity loop delegates ──────────────────────────────────────

        /// <summary>
        /// Called from AvatarController.Update(). Handles mouth open smoothing,
        /// viseme timeline advance, ARKit fading, and ApplyMouthOpen.
        /// </summary>
        public void DoUpdate()
        {
            // Smooth mouth open (FR-LIPSYNC-01: RMS lip sync at 30Hz)
            _currentMouthOpen = Mathf.Lerp(
                _currentMouthOpen, _targetMouthOpen,
                Time.deltaTime * MouthSmoothSpeed);

            bool a2fActive = _a2fLipSync != null && _a2fLipSync.IsReady && _a2fLipSync.IsSpeaking;

            // M21: mode-gated suppression prevents dual-write race condition.
            bool suppressViseme = _lipSyncMode == LipSyncMode.A2FNeural ||
                                  (_lipSyncMode == LipSyncMode.Hybrid && a2fActive);

            if (suppressViseme)
            {
                // A2F drives all ARKit mouth shapes; phoneme system is suppressed.
                // NOTE: ApplyToMesh is called in DoLateUpdate() to run AFTER Animator evaluation.
                _visemePlaying = false;
            }
            else if (_visemePlaying && _visemeEvents != null)
            {
                UpdateViseme();
            }
            else
            {
                // Fade ARKit PerfectSync shapes to zero when not speaking
                FadeARKitToZero();
            }

            // Suppress RMS mouth-open when a dedicated system is writing the mouth shapes.
            bool suppressMouthOpen = _lipSyncMode switch
            {
                LipSyncMode.A2FNeural => a2fActive,
                LipSyncMode.TtsViseme => _visemePlaying,
                _                     => a2fActive || _visemePlaying, // Hybrid
            };
            if (suppressMouthOpen)
                ApplyMouthOpen(0f);
            else
                ApplyMouthOpen(_currentMouthOpen);
        }

        /// <summary>
        /// Called from AvatarController.LateUpdate(). Applies A2F blendshapes after Animator evaluation.
        /// In TtsViseme mode A2F new writes are suppressed, but residual weights are faded to zero
        /// to prevent the mouth freezing open when A2F finishes speaking. (M21 / Re2)
        /// </summary>
        public void DoLateUpdate()
        {
            if (_faceMesh == null) return;
            if (_lipSyncMode == LipSyncMode.TtsViseme)
            {
                // M21: suppress A2F driving mouth during TTS viseme mode.
                // Only fade residual A2F weights when BOTH A2F and TTS viseme are done;
                // calling FadeToZero while viseme is playing overwrites the same vowel
                // blendshapes that UpdateViseme() just wrote (Bug: second sentence silent).
                if (_a2fLipSync != null && _a2fLipSync.IsReady
                    && !_a2fLipSync.IsSpeaking && !_visemePlaying)
                    _a2fLipSync.FadeToZero(_faceMesh);
                return;
            }
            if (_a2fLipSync != null && _a2fLipSync.IsReady)
            {
                if (_a2fLipSync.IsSpeaking)
                    _a2fLipSync.ApplyToMesh(_faceMesh);
                else
                    _a2fLipSync.FadeToZero(_faceMesh);
            }
        }

        // ── Outbound properties (read by AvatarController) ────────────

        /// <summary>True when Audio2FaceLipSync is ready and currently speaking.</summary>
        public bool IsA2FActive => _a2fLipSync != null && _a2fLipSync.IsReady && _a2fLipSync.IsSpeaking;

        /// <summary>Estimated emotion from A2F prosody analysis, or "neutral" if A2F not active.</summary>
        public string EstimatedA2FEmotion => _a2fLipSync?.EstimatedEmotion ?? "neutral";

        /// <summary>Current target mouth open value (0..1) — use to preserve value across ApplyFromPolicy.</summary>
        public float TargetMouthOpen => _targetMouthOpen;

        /// <summary>Current smoothed mouth open value (0..1).</summary>
        public float CurrentMouthOpen => _currentMouthOpen;

        // ── WS message handlers ───────────────────────────────────────

        /// <summary>avatar_viseme (FR-LIPSYNC-02): queue a phoneme timeline.</summary>
        public void HandleViseme(AvatarVisemeParams p)
        {
            if (p == null || p.events == null || p.events.Length == 0)
            {
                Debug.LogWarning($"[LipSync] HandleViseme: null or empty events (p={p})");
                return;
            }
            Debug.Log($"[LipSync] Viseme: {p.events.Length} events, faceMesh={(_faceMesh != null ? _faceMesh.name : "NULL")}, AIdx={_visemeAIndex}");

            // Events must be sorted by t_ms (TC-A7-07)
            Array.Sort(p.events, (a, b) => a.t_ms.CompareTo(b.t_ms));

            _visemeEvents = p.events;
            _visemeIndex = 0;
            _visemeStartTime = Time.time;
            _visemePlaying = true;
            _visemeCrossfadeMs = Mathf.Clamp(p.crossfade_ms, 40f, 80f);
            _visemeStrength = Mathf.Clamp01(p.strength);
        }

        /// <summary>a2f_audio (FR-LIPSYNC-01): push full PCM utterance to Audio2FaceLipSync.</summary>
        public void HandleA2FAudio(A2FAudioParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.pcm_b64))
            {
                Debug.LogWarning("[LipSync] a2f_audio: null or empty pcm_b64");
                return;
            }
            if (_a2fLipSync == null || !_a2fLipSync.IsReady)
            {
                Debug.Log("[LipSync] a2f_audio received but Audio2FaceLipSync is not ready. Ignoring.");
                return;
            }

            byte[] bytes;
            try
            {
                bytes = Convert.FromBase64String(p.pcm_b64);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[LipSync] a2f_audio: base64 decode failed: {ex.Message}");
                return;
            }

            float[] pcm;
            if (string.Equals(p.format, "int16", StringComparison.OrdinalIgnoreCase))
            {
                int samples = bytes.Length / 2;
                pcm = new float[samples];
                for (int i = 0; i < samples; i++)
                {
                    short s = (short)(bytes[i * 2] | (bytes[i * 2 + 1] << 8));
                    pcm[i] = s / 32768f;
                }
            }
            else
            {
                int samples = bytes.Length / 4;
                pcm = new float[samples];
                Buffer.BlockCopy(bytes, 0, pcm, 0, samples * 4); // samples*4 not bytes.Length to guard misaligned payload
            }

            if (p.sample_rate != 16000)
                Debug.LogWarning($"[LipSync] a2f_audio: sample_rate={p.sample_rate} but A2F expects 16000. Audio may be distorted.");

            _a2fLipSync.ProcessAudio(pcm);
        }

        /// <summary>a2f_chunk: push streaming PCM chunk to Audio2FaceLipSync.</summary>
        public void HandleA2FChunk(A2fChunkParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.pcm_b64))
            {
                Debug.LogWarning("[LipSync] a2f_chunk: null or empty pcm_b64");
                return;
            }
            if (_a2fLipSync == null || !_a2fLipSync.IsReady)
            {
                Debug.Log("[LipSync] a2f_chunk received but Audio2FaceLipSync is not ready. Ignoring.");
                return;
            }

            byte[] bytes;
            try
            {
                bytes = Convert.FromBase64String(p.pcm_b64);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[LipSync] a2f_chunk: base64 decode failed: {ex.Message}");
                return;
            }

            float[] pcm;
            if (string.Equals(p.format, "int16", StringComparison.OrdinalIgnoreCase))
            {
                int samples = bytes.Length / 2;
                pcm = new float[samples];
                for (int i = 0; i < samples; i++)
                {
                    short s = (short)(bytes[i * 2] | (bytes[i * 2 + 1] << 8));
                    pcm[i] = s / 32768f;
                }
            }
            else
            {
                int samples = bytes.Length / 4;
                pcm = new float[samples];
                Buffer.BlockCopy(bytes, 0, pcm, 0, samples * 4); // samples*4 not bytes.Length to guard misaligned payload
            }

            if (p.sample_rate != 16000)
                Debug.LogWarning($"[LipSync] a2f_chunk: sample_rate={p.sample_rate} but A2F expects 16000.");

            // Bug C fix: on the first chunk, clear TTS viseme state so A2F has full control.
            if (p.is_first)
            {
                _currentVisemeA = 0f;
                _currentVisemeI = 0f;
                _currentVisemeU = 0f;
                _currentVisemeE = 0f;
                _currentVisemeO = 0f;
                _visemePlaying  = false;
            }

            _a2fLipSync.PushAudioChunk(pcm, p.is_first);
        }

        /// <summary>a2f_stream_close: signal end of streaming utterance.</summary>
        public void HandleA2FStreamClose()
        {
            if (_a2fLipSync == null || !_a2fLipSync.IsReady) return;
            _a2fLipSync.CloseStream();
        }

        /// <summary>avatar_reset: clear all lip sync state immediately.</summary>
        public void HandleReset()
        {
            // Stop any in-progress A2F stream so DoLateUpdate stops driving blend shapes
            _a2fLipSync?.CloseStream();
            _targetMouthOpen = 0f;
            _currentMouthOpen = 0f;
            _visemePlaying = false;
            _visemeEvents = null;
            _currentVisemeA = 0f;
            _currentVisemeI = 0f;
            _currentVisemeU = 0f;
            _currentVisemeE = 0f;
            _currentVisemeO = 0f;
            // Instantly zero all ARKit shapes so mouth doesn't freeze open on reset
            _curJawOpen = _curMouthFunnel = _curMouthPucker = 0f;
            _curMouthLeft = _curMouthRight = 0f;
            _curMouthRollUpper = _curMouthRollLower = 0f;
            _curMouthShrugUpper = _curMouthShrugLower = 0f;
            _curMouthClose = 0f;
            _curMouthSmileL = _curMouthSmileR = 0f;
            _curMouthFrownL = _curMouthFrownR = 0f;
            _curMouthLowerDownL = _curMouthLowerDownR = 0f;
            _curMouthStretchL = _curMouthStretchR = 0f;
            FadeARKitToZero();
        }

        // ── Viseme update (frame-by-frame) ────────────────────────────

        private void UpdateViseme()
        {
            float elapsed_ms = (Time.time - _visemeStartTime) * 1000f;

            // ── Anticipation: advance index when we are VisemeAnticipationMs ahead ──
            while (_visemeIndex < _visemeEvents.Length - 1 &&
                   _visemeEvents[_visemeIndex + 1].t_ms - VisemeAnticipationMs <= elapsed_ms)
            {
                _visemeIndex++;
            }

            if (_visemeIndex >= _visemeEvents.Length)
            {
                _visemePlaying = false;
                ApplyVisemeWeightsDirect(0f, 0f, 0f, 0f, 0f);
                return;
            }

            string currentViseme = _visemeEvents[_visemeIndex].v;

            // ── Coarticulation: blend toward next viseme in the latter part of phoneme ──
            float coBlend = 0f;
            string nextViseme = currentViseme;
            if (_visemeIndex < _visemeEvents.Length - 1)
            {
                float t0 = _visemeEvents[_visemeIndex].t_ms     - VisemeAnticipationMs;
                float t1 = _visemeEvents[_visemeIndex + 1].t_ms - VisemeAnticipationMs;
                float dur = t1 - t0;
                if (dur > 0f)
                {
                    float progress = Mathf.Clamp01((elapsed_ms - t0) / dur);
                    float raw = Mathf.Clamp01((progress - CoarticulationStart)
                                              / (1f - CoarticulationStart));
                    coBlend = raw * raw * (3f - 2f * raw); // smoothstep
                    nextViseme = _visemeEvents[_visemeIndex + 1].v;
                }
            }

            GetVisemeRawWeights(currentViseme, 1f - coBlend,
                                out float tA, out float tI, out float tU, out float tE, out float tO);
            GetVisemeRawWeights(nextViseme, coBlend,
                                out float nA, out float nI, out float nU, out float nE, out float nO);
            ApplyVisemeWeightsDirect(
                (tA + nA) * _visemeStrength,
                (tI + nI) * _visemeStrength,
                (tU + nU) * _visemeStrength,
                (tE + nE) * _visemeStrength,
                (tO + nO) * _visemeStrength);

            ApplyARKitWeights(
                currentViseme, 1f - coBlend,
                nextViseme,    coBlend,
                _visemeStrength * _articulationStrength);

            float targetOpen = VisemeToMouthOpen(currentViseme) * _visemeStrength;
            float crossfadeSec = _visemeCrossfadeMs / 1000f;
            _targetMouthOpen = Mathf.Lerp(
                _targetMouthOpen, targetOpen,
                Time.deltaTime / Mathf.Max(crossfadeSec, 0.01f));

            // ── End detection ──
            if (_visemeIndex == _visemeEvents.Length - 1)
            {
                float lastEventMs = _visemeEvents[_visemeEvents.Length - 1].t_ms;
                if (elapsed_ms > lastEventMs + _visemeCrossfadeMs)
                {
                    _visemePlaying = false;
                    _targetMouthOpen = 0f;
                    ApplyVisemeWeightsDirect(0f, 0f, 0f, 0f, 0f);
                }
            }
        }

        private static void GetVisemeRawWeights(
            string viseme, float strength,
            out float a, out float i, out float u, out float e, out float o)
        {
            a = i = u = e = o = 0f;
            switch (viseme)
            {
                case "a":  a = strength; break;
                case "i":  i = strength; break;
                case "u":  u = strength; break;
                case "e":  e = strength; break;
                case "o":  o = strength; break;
                case "fv": u = strength * 0.3f; break;
                // "sil", "m", unknown → all zero (mouth closed)
            }
        }

        private void ApplyVisemeWeightsDirect(float a, float i, float u, float e, float o)
        {
            if (_faceMesh == null) return;
            const float kScale = 65f; // 0..1 → 0..65 blend-shape range
            float crossfadeSec = Mathf.Max(_visemeCrossfadeMs / 1000f, 0.01f);
            float t = Time.deltaTime / crossfadeSec;
            LerpVisemeWeight(_visemeAIndex, ref _currentVisemeA, a * kScale, t);
            LerpVisemeWeight(_visemeIIndex, ref _currentVisemeI, i * kScale, t);
            LerpVisemeWeight(_visemeUIndex, ref _currentVisemeU, u * kScale, t);
            LerpVisemeWeight(_visemeEIndex, ref _currentVisemeE, e * kScale, t);
            LerpVisemeWeight(_visemeOIndex, ref _currentVisemeO, o * kScale, t);
        }

        private void ApplyVisemeBlendShapes(string viseme, float strength)
        {
            GetVisemeRawWeights(viseme, strength,
                out float a, out float i, out float u, out float e, out float o);
            ApplyVisemeWeightsDirect(a, i, u, e, o);
        }

        private void LerpVisemeWeight(int index, ref float current, float target, float t)
        {
            if (index < 0 || _faceMesh == null) return;
            current = Mathf.Lerp(current, target, t);
            _faceMesh.SetBlendShapeWeight(index, Mathf.Clamp(current, 0f, 100f));
        }

        // ── ARKit PerfectSync drive ───────────────────────────────────

        private void ApplyARKitWeights(string v1, float w1, string v2, float w2, float globalStr)
        {
            if (_faceMesh == null) return;
            if (!s_ArkitProfiles.TryGetValue(v1, out var p1)) p1 = default;
            if (!s_ArkitProfiles.TryGetValue(v2, out var p2)) p2 = default;
            const float kScale = 100f;
            float s = globalStr * kScale;
            float t = Time.deltaTime / Mathf.Max(_visemeCrossfadeMs / 1000f, 0.01f);
            LerpARKit(_jawOpenIndex,          ref _curJawOpen,          (p1.jawOpen          * w1 + p2.jawOpen          * w2) * s, t);
            LerpARKit(_mouthFunnelIndex,      ref _curMouthFunnel,      (p1.mouthFunnel      * w1 + p2.mouthFunnel      * w2) * s, t);
            LerpARKit(_mouthPuckerIndex,      ref _curMouthPucker,      (p1.mouthPucker      * w1 + p2.mouthPucker      * w2) * s, t);
            LerpARKit(_mouthLeftIndex,        ref _curMouthLeft,        (p1.mouthLeft        * w1 + p2.mouthLeft        * w2) * s, t);
            LerpARKit(_mouthRightIndex,       ref _curMouthRight,       (p1.mouthRight       * w1 + p2.mouthRight       * w2) * s, t);
            LerpARKit(_mouthRollUpperIndex,   ref _curMouthRollUpper,   (p1.mouthRollUpper   * w1 + p2.mouthRollUpper   * w2) * s, t);
            LerpARKit(_mouthRollLowerIndex,   ref _curMouthRollLower,   (p1.mouthRollLower   * w1 + p2.mouthRollLower   * w2) * s, t);
            LerpARKit(_mouthShrugUpperIndex,  ref _curMouthShrugUpper,  (p1.mouthShrugUpper  * w1 + p2.mouthShrugUpper  * w2) * s, t);
            LerpARKit(_mouthShrugLowerIndex,  ref _curMouthShrugLower,  (p1.mouthShrugLower  * w1 + p2.mouthShrugLower  * w2) * s, t);
            LerpARKit(_mouthCloseIndex,       ref _curMouthClose,       (p1.mouthClose       * w1 + p2.mouthClose       * w2) * s, t);
            LerpARKit(_mouthSmileLIndex,      ref _curMouthSmileL,      (p1.mouthSmileL      * w1 + p2.mouthSmileL      * w2) * s, t);
            LerpARKit(_mouthSmileRIndex,      ref _curMouthSmileR,      (p1.mouthSmileR      * w1 + p2.mouthSmileR      * w2) * s, t);
            LerpARKit(_mouthFrownLIndex,      ref _curMouthFrownL,      (p1.mouthFrownL      * w1 + p2.mouthFrownL      * w2) * s, t);
            LerpARKit(_mouthFrownRIndex,      ref _curMouthFrownR,      (p1.mouthFrownR      * w1 + p2.mouthFrownR      * w2) * s, t);
            LerpARKit(_mouthLowerDownLIndex,  ref _curMouthLowerDownL,  (p1.mouthLowerDownL  * w1 + p2.mouthLowerDownL  * w2) * s, t);
            LerpARKit(_mouthLowerDownRIndex,  ref _curMouthLowerDownR,  (p1.mouthLowerDownR  * w1 + p2.mouthLowerDownR  * w2) * s, t);
            LerpARKit(_mouthStretchLIndex,    ref _curMouthStretchL,    (p1.mouthStretchL    * w1 + p2.mouthStretchL    * w2) * s, t);
            LerpARKit(_mouthStretchRIndex,    ref _curMouthStretchR,    (p1.mouthStretchR    * w1 + p2.mouthStretchR    * w2) * s, t);
        }

        private void FadeARKitToZero()
        {
            if (_faceMesh == null) return;
            float t = Time.deltaTime / Mathf.Max(_visemeCrossfadeMs / 1000f, 0.01f);
            LerpARKit(_jawOpenIndex,          ref _curJawOpen,          0f, t);
            LerpARKit(_mouthFunnelIndex,      ref _curMouthFunnel,      0f, t);
            LerpARKit(_mouthPuckerIndex,      ref _curMouthPucker,      0f, t);
            LerpARKit(_mouthLeftIndex,        ref _curMouthLeft,        0f, t);
            LerpARKit(_mouthRightIndex,       ref _curMouthRight,       0f, t);
            LerpARKit(_mouthRollUpperIndex,   ref _curMouthRollUpper,   0f, t);
            LerpARKit(_mouthRollLowerIndex,   ref _curMouthRollLower,   0f, t);
            LerpARKit(_mouthShrugUpperIndex,  ref _curMouthShrugUpper,  0f, t);
            LerpARKit(_mouthShrugLowerIndex,  ref _curMouthShrugLower,  0f, t);
            LerpARKit(_mouthCloseIndex,       ref _curMouthClose,       0f, t);
            LerpARKit(_mouthSmileLIndex,      ref _curMouthSmileL,      0f, t);
            LerpARKit(_mouthSmileRIndex,      ref _curMouthSmileR,      0f, t);
            LerpARKit(_mouthFrownLIndex,      ref _curMouthFrownL,      0f, t);
            LerpARKit(_mouthFrownRIndex,      ref _curMouthFrownR,      0f, t);
            LerpARKit(_mouthLowerDownLIndex,  ref _curMouthLowerDownL,  0f, t);
            LerpARKit(_mouthLowerDownRIndex,  ref _curMouthLowerDownR,  0f, t);
            LerpARKit(_mouthStretchLIndex,    ref _curMouthStretchL,    0f, t);
            LerpARKit(_mouthStretchRIndex,    ref _curMouthStretchR,    0f, t);
        }

        private void LerpARKit(int index, ref float current, float target, float t)
        {
            if (index < 0 || _faceMesh == null) return;
            current = Mathf.Lerp(current, target, t);
            _faceMesh.SetBlendShapeWeight(index, Mathf.Clamp(current, 0f, 100f));
        }

        private static float VisemeToMouthOpen(string viseme)
        {
            return viseme switch
            {
                "sil" => 0.0f,
                "a"   => 0.5f,
                "i"   => 0.2f,
                "u"   => 0.25f,
                "e"   => 0.3f,
                "o"   => 0.4f,
                "m"   => 0.05f,
                "fv"  => 0.1f,
                _     => 0.0f, // Unknown viseme: safe default
            };
        }

        private void ApplyMouthOpen(float value)
        {
            if (_faceMesh == null || _mouthOpenBlendIndex < 0) return;
            _faceMesh.SetBlendShapeWeight(
                _mouthOpenBlendIndex,
                Mathf.Clamp(value * _mouthSensitivity * 100f, 0f, 100f));
        }

        // ── ARKit index helpers ───────────────────────────────────────

        /// <summary>
        /// Right-click the component in the Inspector and select this to
        /// auto-fill all ARKit indices for the QuQu avatar (blendshapes.txt values).
        /// </summary>
        [ContextMenu("Auto-Config ARKit Indices (QuQu defaults)")]
        private void AutoConfigARKitIndicesQuQu()
        {
            _jawOpenIndex         = 78;
            _mouthFunnelIndex     = 82;
            _mouthPuckerIndex     = 83;
            _mouthLeftIndex       = 84;
            _mouthRightIndex      = 85;
            _mouthRollUpperIndex  = 86;
            _mouthRollLowerIndex  = 87;
            _mouthShrugUpperIndex = 88;
            _mouthShrugLowerIndex = 89;
            _mouthCloseIndex      = 90;
            _mouthSmileLIndex     = 91;
            _mouthSmileRIndex     = 92;
            _mouthFrownLIndex     = 93;
            _mouthFrownRIndex     = 94;
            _mouthLowerDownLIndex = 99;
            _mouthLowerDownRIndex = 100;
            _mouthStretchLIndex   = 103;
            _mouthStretchRIndex   = 104;
            Debug.Log("[LipSync] ARKit indices auto-configured for QuQu avatar.");
#if UNITY_EDITOR
            UnityEditor.EditorUtility.SetDirty(this);
#endif
        }

        private void AutoDetectArkitIndices()
        {
            var mesh = _faceMesh.sharedMesh;
            int count = mesh.blendShapeCount;

            var map = new Dictionary<string, Action<int>>(StringComparer.OrdinalIgnoreCase)
            {
                { "jawOpen",           v => _jawOpenIndex         = v },
                { "mouthFunnel",       v => _mouthFunnelIndex     = v },
                { "mouthPucker",       v => _mouthPuckerIndex     = v },
                { "mouthLeft",         v => _mouthLeftIndex       = v },
                { "mouthRight",        v => _mouthRightIndex      = v },
                { "mouthRollUpper",    v => _mouthRollUpperIndex  = v },
                { "mouthRollLower",    v => _mouthRollLowerIndex  = v },
                { "mouthShrugUpper",   v => _mouthShrugUpperIndex = v },
                { "mouthShrugLower",   v => _mouthShrugLowerIndex = v },
                { "mouthClose",        v => _mouthCloseIndex      = v },
                { "mouthSmile_L",      v => _mouthSmileLIndex     = v },
                { "mouthSmile_R",      v => _mouthSmileRIndex     = v },
                { "mouthFrown_L",      v => _mouthFrownLIndex     = v },
                { "mouthFrown_R",      v => _mouthFrownRIndex     = v },
                { "mouthLowerDown_L",  v => _mouthLowerDownLIndex = v },
                { "mouthLowerDown_R",  v => _mouthLowerDownRIndex = v },
                { "mouthStretch_L",    v => _mouthStretchLIndex   = v },
                { "mouthStretch_R",    v => _mouthStretchRIndex   = v },
            };
            var aliases = new Dictionary<string, Action<int>>(StringComparer.OrdinalIgnoreCase)
            {
                { "mouthSmileLeft",      v => _mouthSmileLIndex     = v },
                { "mouthSmileRight",     v => _mouthSmileRIndex     = v },
                { "mouthFrownLeft",      v => _mouthFrownLIndex     = v },
                { "mouthFrownRight",     v => _mouthFrownRIndex     = v },
                { "mouthLowerDownLeft",  v => _mouthLowerDownLIndex = v },
                { "mouthLowerDownRight", v => _mouthLowerDownRIndex = v },
                { "mouthStretchLeft",    v => _mouthStretchLIndex   = v },
                { "mouthStretchRight",   v => _mouthStretchRIndex   = v },
            };

            for (int i = 0; i < count; i++)
            {
                string name = mesh.GetBlendShapeName(i);
                if (map.TryGetValue(name, out var setter))       { setter(i); continue; }
                if (aliases.TryGetValue(name, out var setter2))  { setter2(i); }
            }

            int found = 0;
            for (int i = 0; i < count; i++)
            {
                string n = mesh.GetBlendShapeName(i);
                if (map.ContainsKey(n) || aliases.ContainsKey(n)) found++;
            }
            Debug.Log($"[LipSync] ARKit auto-detect: jawOpen={_jawOpenIndex} mouthSmileL={_mouthSmileLIndex} ({found} shapes matched on '{_faceMesh.name}')");
        }

        // ── Test seams ────────────────────────────────────────────────
        // These properties/methods exist solely for EditMode unit tests.

        public bool         IsVisemePlayingForTest  => _visemePlaying;
        public float        TargetMouthOpenForTest  => _targetMouthOpen;
        public float        CurrentMouthOpenForTest => _currentMouthOpen;
        public float        MouthSensitivityForTest => _mouthSensitivity;
        public LipSyncMode  LipSyncModeForTest      => _lipSyncMode;
        public void  SetFaceMeshForTest(SkinnedMeshRenderer mesh) => _faceMesh = mesh;
        public void  SetA2FLipSyncForTest(Audio2FaceLipSync a2f)  => _a2fLipSync = a2f;
    }
}

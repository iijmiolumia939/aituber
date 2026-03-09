// LipSyncController.cs
// LipSync (3-mode: RMS mouth_open / phoneme viseme / Audio2Face neural) + ARKit PerfectSync.
// Extracted from AvatarController.cs (Issue #52, Phase 4 窶・Strangler Fig).
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
        // 笏笏 SerializedFields 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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

        [Header("ARKit PerfectSync Blendshape Driver (Issue #52)")]
        [Tooltip("Auto-wired in Awake(). Point to a pre-configured component to preserve QuQu indices.")]
        [SerializeField] private ARKitBlendShapeDriver _arkitDriver;

        [Header("LipSync Mode (M21)")]
        [Tooltip("A2FNeural: only A2F drives mouth (TTS viseme suppressed). [default, best quality with A2F v3.0+]\n"
               + "TtsViseme: only TTS phoneme viseme drives mouth (A2F muted).\n"
               + "Hybrid: A2F has precedence while IsSpeaking; viseme drives otherwise.")]
        [SerializeField] private LipSyncMode _lipSyncMode = LipSyncMode.A2FNeural;

        [Header("Audio2Face Neural Lip Sync (optional)")]
        [Tooltip("Optional Audio2FaceLipSync component for neural blendshape generation. "
               + "When set and active, a2f_audio WS commands bypass the phoneme-based lip sync.")]
        [SerializeField] private Audio2FaceLipSync _a2fLipSync;

        // 笏笏 Mouth open state (FR-LIPSYNC-01) 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

        private float _targetMouthOpen;
        private float _currentMouthOpen;
        private const float MouthSmoothSpeed = 20f;
        private float _mouthSensitivity = 1f;

        // 笏笏 Viseme state (FR-LIPSYNC-02) 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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


        // 笏笏 Lifecycle 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

        private void Awake()
        {
            if (_a2fLipSync == null)
                _a2fLipSync = GetComponent<Audio2FaceLipSync>();
            if (_arkitDriver == null)
                _arkitDriver = GetComponent<ARKitBlendShapeDriver>() ?? gameObject.AddComponent<ARKitBlendShapeDriver>();
        }

        // 笏笏 Initialization 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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

            _arkitDriver.Initialize(_faceMesh);

            if (_a2fLipSync != null)
            {
                _a2fLipSync.SetIndexMap(
                    _arkitDriver.JawOpen,
                    _arkitDriver.MouthFunnel,    _arkitDriver.MouthPucker,
                    _arkitDriver.MouthLeft,      _arkitDriver.MouthRight,
                    _arkitDriver.MouthRollUpper, _arkitDriver.MouthRollLower,
                    _arkitDriver.MouthShrugUpper, _arkitDriver.MouthShrugLower,
                    _arkitDriver.MouthClose,
                    _arkitDriver.MouthSmileL,    _arkitDriver.MouthSmileR,
                    _arkitDriver.MouthFrownL,    _arkitDriver.MouthFrownR,
                    _arkitDriver.MouthLowerDownL, _arkitDriver.MouthLowerDownR,
                    _arkitDriver.MouthStretchL,  _arkitDriver.MouthStretchR);
                _a2fLipSync.SetVowelMap(
                    _visemeAIndex, _visemeIIndex, _visemeUIndex,
                    _visemeEIndex, _visemeOIndex);
                Debug.Log($"[LipSync] Audio2FaceLipSync index map wired. jawOpen={_arkitDriver.JawOpen}");
            }
        }

        // 笏笏 Config 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

        /// <summary>Switch lip sync drive mode at runtime (M21 / Issue #56).</summary>
        public void SetLipSyncMode(LipSyncMode mode) => _lipSyncMode = mode;

        public void SetMouthSensitivity(float v) => _mouthSensitivity = v;

        /// <summary>Set mouth open target from avatar_update mouth_open (FR-LIPSYNC-01).</summary>
        public void SetMouthOpen(float v) => _targetMouthOpen = Mathf.Clamp01(v);

        // 笏笏 Unity loop delegates 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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
                _arkitDriver.SetCrossfadeMs(_visemeCrossfadeMs);
                _arkitDriver.FadeToZero();
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

        // 笏笏 Outbound properties (read by AvatarController) 笏笏笏笏笏笏笏笏笏笏笏笏

        /// <summary>True when Audio2FaceLipSync is ready and currently speaking.</summary>
        public bool IsA2FActive => _a2fLipSync != null && _a2fLipSync.IsReady && _a2fLipSync.IsSpeaking;

        /// <summary>Estimated emotion from A2F prosody analysis, or "neutral" if A2F not active.</summary>
        public string EstimatedA2FEmotion => _a2fLipSync?.EstimatedEmotion ?? "neutral";

        /// <summary>Current target mouth open value (0..1) 窶・use to preserve value across ApplyFromPolicy.</summary>
        public float TargetMouthOpen => _targetMouthOpen;

        /// <summary>Current smoothed mouth open value (0..1).</summary>
        public float CurrentMouthOpen => _currentMouthOpen;

        // 笏笏 WS message handlers 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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
            _arkitDriver.ResetState();
        }

        // 笏笏 Viseme update (frame-by-frame) 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

        private void UpdateViseme()
        {
            float elapsed_ms = (Time.time - _visemeStartTime) * 1000f;

            // 笏笏 Anticipation: advance index when we are VisemeAnticipationMs ahead 笏笏
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

            // 笏笏 Coarticulation: blend toward next viseme in the latter part of phoneme 笏笏
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

            _arkitDriver.SetCrossfadeMs(_visemeCrossfadeMs);
            _arkitDriver.Apply(currentViseme, 1f - coBlend, nextViseme, coBlend, _visemeStrength);

            float targetOpen = VisemeToMouthOpen(currentViseme) * _visemeStrength;
            float crossfadeSec = _visemeCrossfadeMs / 1000f;
            _targetMouthOpen = Mathf.Lerp(
                _targetMouthOpen, targetOpen,
                Time.deltaTime / Mathf.Max(crossfadeSec, 0.01f));

            // 笏笏 End detection 笏笏
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
                // "sil", "m", unknown 竊・all zero (mouth closed)
            }
        }

        private void ApplyVisemeWeightsDirect(float a, float i, float u, float e, float o)
        {
            if (_faceMesh == null) return;
            const float kScale = 65f; // 0..1 竊・0..65 blend-shape range
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
        // 笏笏 Test seams 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
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

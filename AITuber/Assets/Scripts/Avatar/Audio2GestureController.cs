// Audio2GestureController.cs
// MonoBehaviour that manages the Audio2Gesture native plugin lifecycle.
// Accepts 16kHz PCM audio, runs neural gesture inference, and applies
// upper-body bone rotation deltas to the humanoid Animator rig each frame.
//
// Usage:
//   1. Ensure A2GPlugin.dll is in Assets/Plugins/x86_64/ (build from native/A2GPlugin/).
//   2. Add this component to the same GameObject as AvatarController.
//   3. AvatarController calls ApplyToRig(animator) in LateUpdate.
//   4. Call PushAudioChunk(pcm) / CloseStream() alongside A2F for dual gesture+lipsync.
//
// Graceful degradation:
//   If A2GPlugin.dll is absent, IsReady == false and all methods are safe no-ops.
//
// SRS refs: FR-GESTURE-AUTO-01

using System;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Manages the A2GPlugin native-DLL lifecycle and provides per-frame
    /// upper-body bone rotation deltas to AvatarController.
    /// </summary>
    public class Audio2GestureController : MonoBehaviour
    {
        // ── Inspector ────────────────────────────────────────────────

        [Tooltip("Output frame rate numerator (should match Unity's target FPS).")]
        [SerializeField] private int _frameRateNum = 30;

        [Tooltip("Output frame rate denominator (usually 1).")]
        [SerializeField] private int _frameRateDen = 1;

        [Header("Runtime")]
        [Tooltip("Blend weight for additive gesture application (0=disabled, 1=full A2G).")]
        [Range(0f, 1f)]
        [SerializeField] private float _gestureStrength = 0.7f;

        [Tooltip("Lerp speed for smoothing bone rotations (per second).")]
        [SerializeField] private float _smoothSpeed = 12f;

        // ── Bone layout ──────────────────────────────────────────────
        // A2G upper-body bone order (13 joints).
        // Must match the order defined in the A2G model bundle.
        private static readonly HumanBodyBones[] s_BoneMap = new HumanBodyBones[]
        {
            HumanBodyBones.Spine,
            HumanBodyBones.Chest,
            HumanBodyBones.UpperChest,
            HumanBodyBones.Neck,
            HumanBodyBones.Head,
            HumanBodyBones.LeftShoulder,
            HumanBodyBones.LeftUpperArm,
            HumanBodyBones.LeftLowerArm,
            HumanBodyBones.LeftHand,
            HumanBodyBones.RightShoulder,
            HumanBodyBones.RightUpperArm,
            HumanBodyBones.RightLowerArm,
            HumanBodyBones.RightHand,
        };
        private const int kBoneCount = 13;

        // ── State ────────────────────────────────────────────────────

        private IntPtr _handle = IntPtr.Zero;
        private bool   _pluginReady;

        // Per-bone buffers (no per-frame allocation)
        private float[]      _quatBuf;          // raw output: kBoneCount * 4
        private Quaternion[] _targetBoneRots;   // last A2G delta (held across frames)
        private Quaternion[] _smoothBoneRots;   // current interpolated deltas
        private Quaternion[] _neutralBoneRots;  // neutral pose captured in Start()
        private Transform[]  _boneTransforms;   // cached bone transforms from Animator

        // Rate-limiter (same logic as Audio2FaceLipSync)
        private float _nextFrameTime = 0f;

        private bool _isSpeaking;
        private float _speakingEndTime = float.MaxValue;
        private bool _hasNewRotations;

        // Neutral pose is captured lazily on the first ApplyToRig call (LateUpdate),
        // which runs AFTER the Animator has evaluated. Capturing at Start() would get
        // T-pose because the Animator hasn't played yet at that point.
        private bool _neutralCaptured;

        // ── Properties ───────────────────────────────────────────────

        /// <summary>True if A2GPlugin.dll is loaded and the plugin handle is valid.</summary>
        public bool IsReady => _pluginReady;

        /// <summary>True while A2G is actively generating gesture data.</summary>
        public bool IsSpeaking => _isSpeaking;

        // ── Lifecycle ────────────────────────────────────────────────

        private void Awake()
        {
            _quatBuf         = new float[kBoneCount * 4];
            _targetBoneRots  = new Quaternion[kBoneCount];
            _smoothBoneRots  = new Quaternion[kBoneCount];
            _neutralBoneRots = new Quaternion[kBoneCount];
            _boneTransforms  = new Transform[kBoneCount];
            for (int i = 0; i < kBoneCount; i++)
            {
                _targetBoneRots[i] = Quaternion.identity;
                _smoothBoneRots[i] = Quaternion.identity;
            }
        }

        private void OnEnable()
        {
            if (_pluginReady) return;

            // ── Native plugin path ────────────────────────────────────────────────────
            // A2GPlugin.dll is a standalone audio-energy engine (RMS/IIR — no TRT).
            // Safe to load directly in both Editor and Standalone builds.
            try
            {
                if (!Audio2GesturePlugin.IsAvailable)
                {
                    Debug.LogWarning("[A2GCtrl] A2GPlugin not available — skipping init.");
                    return;
                }

                _handle = Audio2GesturePlugin.A2GPlugin_Create(
                    null,
                    0,
                    _frameRateNum,
                    _frameRateDen);

                if (_handle == IntPtr.Zero)
                {
                    Debug.LogError("[A2GCtrl] A2GPlugin_Create returned null handle.");
                    return;
                }

                if (Audio2GesturePlugin.A2GPlugin_IsValid(_handle) == 0)
                {
                    string err = Audio2GesturePlugin.A2GPlugin_GetLastError(_handle);
                    Debug.LogError($"[A2GCtrl] Plugin not valid after create: {err}");
                    Audio2GesturePlugin.A2GPlugin_Destroy(_handle);
                    _handle = IntPtr.Zero;
                    return;
                }

                _pluginReady = true;
                Debug.Log($"[A2GCtrl] Plugin ready. BoneCount={Audio2GesturePlugin.A2GPlugin_GetBoneCount(_handle)}");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[A2GCtrl] Exception during init:\n{ex}");
            }
        }

        private void OnDisable()
        {
            if (_handle != IntPtr.Zero)
            {
                Audio2GesturePlugin.A2GPlugin_Destroy(_handle);
                _handle = IntPtr.Zero;
            }
            _pluginReady       = false;
            _neutralCaptured   = false;  // Re-capture on next enable so Animator pose is fresh
            _isSpeaking        = false;
        }

        private void Update()
        {
            if (_pluginReady)
            {
                int framesReady = Audio2GesturePlugin.A2GPlugin_HasFrameReady(_handle);
                if (framesReady > 0 && Time.time >= _nextFrameTime)
                {
                    // A2GPlugin_ProcessFrame returns queue depth (≥1) on success, <0 on error.
                    int rc = Audio2GesturePlugin.A2GPlugin_ProcessFrame(_handle);
                    if (rc < 0)
                    {
                        string err = Audio2GesturePlugin.A2GPlugin_GetLastError(_handle);
                        Debug.LogWarning($"[A2GCtrl] ProcessFrame error {rc}: {err}");
                    }
                    _nextFrameTime = Time.time + (float)_frameRateDen / _frameRateNum;
                }

                long tsUs = 0;
                int n = Audio2GesturePlugin.A2GPlugin_GetLatestBoneRotations(
                    _handle, _quatBuf, kBoneCount, out tsUs);
                if (n > 0)
                {
                    _hasNewRotations = true;
                    for (int i = 0; i < n && i < kBoneCount; i++)
                    {
                        int b = i * 4;
                        _targetBoneRots[i] = new Quaternion(
                            _quatBuf[b], _quatBuf[b+1], _quatBuf[b+2], _quatBuf[b+3]);
                    }
                }
            }

            if (_isSpeaking && Time.time > _speakingEndTime)
            {
                _isSpeaking       = false;
                _hasNewRotations  = false;
            }
        }

        // ── Public API ───────────────────────────────────────────────

        /// <summary>
        /// Cache neutral bone transforms from the Animator.
        /// Call once from AvatarController.Start() after Animator is ready.
        /// </summary>
        public void CaptureNeutralPose(Animator animator)
        {
            if (animator == null) return;
            for (int i = 0; i < kBoneCount; i++)
            {
                Transform t = animator.GetBoneTransform(s_BoneMap[i]);
                _boneTransforms[i]  = t;
                _neutralBoneRots[i] = t != null ? t.localRotation : Quaternion.identity;
            }
            Debug.Log("[A2GCtrl] Neutral pose captured.");
        }

        /// <summary>
        /// Push a chunk of streaming 16 kHz mono float32 PCM.
        /// Pair with <see cref="CloseStream"/> when the utterance ends.
        /// </summary>
        public void PushAudioChunk(float[] pcm16kHz, bool isFirst = false)
        {
            if (pcm16kHz == null || pcm16kHz.Length == 0) return;
            if (!_pluginReady) return;

            if (isFirst)
            {
                Audio2GesturePlugin.A2GPlugin_Reset(_handle);
                _nextFrameTime   = 0f;
                _speakingEndTime = 0f;
            }

            Audio2GesturePlugin.A2GPlugin_PushAudio(_handle, pcm16kHz, pcm16kHz.Length);

            _isSpeaking = true;
            _speakingEndTime = Mathf.Max(_speakingEndTime,
                Time.time + pcm16kHz.Length / 16000f + 0.5f);
        }

        /// <summary>Close the streaming audio accumulator for the current utterance.</summary>
        public void CloseStream()
        {
            if (_pluginReady)
                Audio2GesturePlugin.A2GPlugin_CloseAudio(_handle);
        }

        // Phase 4: LookAt influence set by AvatarController before ApplyToRig each frame.
        // Reduces A2G weight on Head/Neck bones proportionally to avoid competing with
        // OnAnimatorIK's LookAt pass. Range 0..1 (0 = no reduction, 1 = full LookAt active).
        private float _lookAtInfluence;

        /// <summary>
        /// Inform A2G of the current LookAt IK strength so Head/Neck deltas are reduced
        /// to avoid fighting the LookAt IK that ran in OnAnimatorIK this frame.
        /// Call from AvatarController.LateUpdate() before ApplyToRig. Phase 4.
        /// </summary>
        public void SetLookAtInfluence(float weight) => _lookAtInfluence = Mathf.Clamp01(weight);

        /// <summary>
        /// Advance the smoothed bone-delta state without writing to bones.
        /// Phase 4 architecture: A2G computes deltas; the unified bone-application
        /// window (AvatarController.LateUpdate) applies them via ApplyBoneDeltas.
        /// Called internally by ApplyToRig; exposed for callers that want to decouple
        /// compute from apply.
        /// </summary>
        public void SampleDeltas()
        {
            if (!_pluginReady) return;
            float t = Time.deltaTime * _smoothSpeed;
            if (_isSpeaking)
            {
                for (int i = 0; i < kBoneCount; i++)
                {
                    _smoothBoneRots[i] = _hasNewRotations
                        ? Quaternion.Slerp(_smoothBoneRots[i], _targetBoneRots[i],  t)
                        : Quaternion.Slerp(_smoothBoneRots[i], Quaternion.identity, t);
                }
            }
            else
            {
                // Not speaking: fade all deltas toward identity so next onset starts clean.
                for (int i = 0; i < kBoneCount; i++)
                    _smoothBoneRots[i] = Quaternion.Slerp(_smoothBoneRots[i], Quaternion.identity, t);
            }
            _hasNewRotations = false;
        }

        /// <summary>
        /// Write current smoothed bone deltas additively to the rig.
        /// Call after SampleDeltas(). headNeckScale reduces the Head/Neck contribution
        /// (bone indices 3 and 4) when LookAt IK is concurrently active, preventing
        /// the two systems from fighting each other. Phase 4.
        /// </summary>
        public void ApplyBoneDeltas(Animator animator, float headNeckScale = 1f)
        {
            if (animator == null || !IsReady) return;
            if (_boneTransforms[0] == null) CaptureNeutralPose(animator);

            float targetFade = _isSpeaking ? _gestureStrength * _emotionGestureScale : 0f;
            for (int i = 0; i < kBoneCount; i++)
            {
                Transform bone = _boneTransforms[i];
                if (bone == null) continue;

                // Reduce A2G head/neck influence proportionally to LookAt IK weight (Phase 4).
                float scale = (i == 3 || i == 4) ? headNeckScale : 1f;

                // Additive blend on top of the CURRENT Animator output:
                //   bone.localRotation is set by the Animator before LateUpdate runs,
                //   so reading it here gives the correct animated base pose.
                //   Multiplying by delta keeps this purely additive — when delta is
                //   Quaternion.identity the bone is left unchanged.
                Quaternion delta = Quaternion.Slerp(
                    Quaternion.identity, _smoothBoneRots[i], targetFade * scale);
                bone.localRotation = bone.localRotation * delta;
            }
        }

        /// <summary>
        /// Apply current A2G bone rotation deltas to the humanoid rig.
        /// Call every frame from AvatarController.LateUpdate() when A2G is active.
        /// Rotations are applied as additive offsets on top of the Animator base pose.
        /// Phase 4: internally delegates to SampleDeltas() + ApplyBoneDeltas() with
        /// LookAt influence scaling on Head/Neck bones.
        /// </summary>
        public void ApplyToRig(Animator animator)
        {
            if (animator == null) return;
            if (!IsReady) return;

            // Ensure bone transform references are cached (populated by CaptureNeutralPose).
            // If called before AvatarController.Start(), populate now.
            if (_boneTransforms[0] == null)
                CaptureNeutralPose(animator);

            SampleDeltas();

            // Early-out: not speaking — SampleDeltas already faded smoothBoneRots toward
            // identity; no bone writes needed (delta would be Quaternion.identity anyway).
            if (!_isSpeaking) return;

            // Reduce Head/Neck A2G influence by 60% of LookAt weight to prevent the two
            // systems from fighting over the same bones (Phase 4).
            float headNeckScale = 1f - Mathf.Clamp01(_lookAtInfluence * 0.6f);
            ApplyBoneDeltas(animator, headNeckScale);
        }

        /// <summary>Stop A2G processing and fade the rig back to neutral pose.</summary>
        public void StopGesture()
        {
            _isSpeaking      = false;
            _hasNewRotations = false;
            _speakingEndTime = float.MaxValue;
        }

        // ── Emotion-driven gesture intensity (FR-A2E-01) ─────────────────────

        // Scale applied on top of _gestureStrength when emotion is detected.
        // Set by AvatarController when a2e_emotion is received.
        private float _emotionGestureScale = 1.0f;

        /// <summary>
        /// Adjusts gesture intensity based on detected speech emotion (FR-A2E-01).
        /// Called by AvatarController.HandleA2EEmotion when an a2e_emotion command arrives.
        /// Scale is multiplied with the base _gestureStrength in ApplyBoneDeltas.
        /// Suggested mappings: happy→1.2, angry→1.0, neutral→0.7, sad→0.4.
        /// </summary>
        public void SetEmotionGestureScale(float scale) =>
            _emotionGestureScale = Mathf.Clamp(scale, 0f, 2f);

        // FR-GESTURE-AUTO-01: WS a2g_chunk helpers (moved from AvatarController, Issue #52)
        public void HandleA2GChunk(A2gChunkParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.pcm_b64) || !IsReady) return;
            byte[] bytes;
            try { bytes = Convert.FromBase64String(p.pcm_b64); } catch { return; }
            float[] pcm;
            if (string.Equals(p.format, "int16", StringComparison.OrdinalIgnoreCase))
            {
                int n = bytes.Length / 2; pcm = new float[n];
                for (int i = 0; i < n; i++) pcm[i] = (short)(bytes[i * 2] | (bytes[i * 2 + 1] << 8)) / 32768f;
            }
            else { int n = bytes.Length / 4; pcm = new float[n]; Buffer.BlockCopy(bytes, 0, pcm, 0, bytes.Length); }
            PushAudioChunk(pcm, p.is_first);
        }
        public void HandleA2GStreamClose() => CloseStream();
    }
}

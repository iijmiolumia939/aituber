// Audio2FaceLipSync.cs
// MonoBehaviour that manages the Audio2Face-3D native plugin lifecycle.
// Loads the model from a configurable path, accepts 16kHz PCM audio,
// runs inference on demand, and exposes ARKit-52 blendshape weights.
//
// Usage:
//   1. Add this component to the same GameObject as AvatarController.
//   2. Set ModelJsonPath to the absolute path of the A2F model.json.
//   3. AvatarController reads _a2fLipSync.ApplyWeightsTo(faceMesh, indexMap) each frame.
//   4. Call ProcessAudio(float[] pcm16kHz) to feed a TTS utterance.
//
// SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02

using System;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Manages the A2FPlugin native-DLL lifecycle and provides per-frame
    /// ARKit-52 blendshape weights to AvatarController.
    /// </summary>
    public class Audio2FaceLipSync : MonoBehaviour
    {
        // ── Inspector ────────────────────────────────────────────────

        [Header("Audio2Face-3D Model")]
        [Tooltip("Absolute path to the A2F model.json. "
               + "Single-char (v2.x): .../.../mark/model.json\n"
               + "Multi-char (v3.0):  .../audio2face-3d-v3.0/model.json  → character selected by Character Index.")]
        [SerializeField] private string _modelJsonPath = "";

        [Tooltip("Character index for multi-character A2F v3.0 model.json.\n"
               + "0 = Claire, 1 = James, 2 = Mark (ignored for single-character v2.x models).")]
        [Range(0, 2)]
        [SerializeField] private int _characterIndex = 0;

        [Tooltip("Use GPU blendshape solve (recommended for real-time).")]
        [SerializeField] private bool _useGpuSolver = true;

        [Tooltip("Output frame rate numerator (should match Unity's target FPS).")]
        [SerializeField] private int _frameRateNum = 30;

        [Tooltip("Output frame rate denominator (usually 1).")]
        [SerializeField] private int _frameRateDen = 1;

        [Header("Runtime")]
        [Tooltip("Global scale applied to all A2F weights before writing to blendshapes. "
               + "1.0 = raw A2F output (recommended when LipSyncMode=A2FNeural). "
               + "Increase only if mouth movement looks too small.")]
        [Range(0f, 5f)]
        [SerializeField] private float _globalStrength = 1.0f;

        [Tooltip("Lerp speed when fading A2F weights in/out (frames per second unit).")]
        [SerializeField] private float _smoothSpeed = 15f;

        // ── ARKit 52 → QuQu blendshape index map ─────────────────────
        // Standard ARKit order (indices 0..51) mapped to Unity blendshape indices.
        // Only the 18 mouth-related shapes used by AvatarController are wired.
        // Unused shapes default to -1 (not applied).
        //
        // ARKit index → name
        //  24: jawOpen        31: mouthFunnel    37: mouthPucker
        //  32: mouthLeft      38: mouthRight     40: mouthRollUpper
        //  39: mouthRollLower 42: mouthShrugUpper 41: mouthShrugLower
        //  26: mouthClose     43: mouthSmileLeft  44: mouthSmileRight
        //  29: mouthFrownLeft 30: mouthFrownRight 33: mouthLowerDownLeft
        //  34: mouthLowerDownRight 45: mouthStretchLeft 46: mouthStretchRight

        [Header("ARKit Blendshape Index Map (set from AvatarController)")]
        // These are set programmatically by AvatarController; not edited in Inspector.
        [HideInInspector] public int JawOpenIndex           = -1;
        [HideInInspector] public int MouthFunnelIndex       = -1;
        [HideInInspector] public int MouthPuckerIndex       = -1;
        [HideInInspector] public int MouthLeftIndex         = -1;
        [HideInInspector] public int MouthRightIndex        = -1;
        [HideInInspector] public int MouthRollUpperIndex    = -1;
        [HideInInspector] public int MouthRollLowerIndex    = -1;
        [HideInInspector] public int MouthShrugUpperIndex   = -1;
        [HideInInspector] public int MouthShrugLowerIndex   = -1;
        [HideInInspector] public int MouthCloseIndex        = -1;
        [HideInInspector] public int MouthSmileLIndex       = -1;
        [HideInInspector] public int MouthSmileRIndex       = -1;
        [HideInInspector] public int MouthFrownLIndex       = -1;
        [HideInInspector] public int MouthFrownRIndex       = -1;
        [HideInInspector] public int MouthLowerDownLIndex   = -1;
        [HideInInspector] public int MouthLowerDownRIndex   = -1;
        [HideInInspector] public int MouthStretchLIndex     = -1;
        [HideInInspector] public int MouthStretchRIndex     = -1;

        [Header("Vowel Blendshape Indices (set from AvatarController)")]
        // When set, A2F weights are also remapped to vowel shapes for
        // larger, more readable mouth movement (same shapes used by TTS lip sync).
        [HideInInspector] public int VowelAIndex = -1;  // Fcl_MTH_A / あ
        [HideInInspector] public int VowelIIndex = -1;  // Fcl_MTH_I / い
        [HideInInspector] public int VowelUIndex = -1;  // Fcl_MTH_U / う
        [HideInInspector] public int VowelEIndex = -1;  // Fcl_MTH_E / え
        [HideInInspector] public int VowelOIndex = -1;  // Fcl_MTH_O / お

        // ── State ────────────────────────────────────────────────────

        private IntPtr _handle = IntPtr.Zero;
        private bool   _pluginReady;

        // ARKit 52 weight buffer (no per-frame allocation)
        private float[] _weightsBuf;
        private float[] _smoothWeights;  // current interpolated weights applied to mesh
        private float[] _targetWeights;  // last A2F target (held across frames with no new data)
        private const int kArKitCount = 52;

        // Whether we are currently in "speaking" mode (audio was pushed, not yet reset)
        private bool   _isSpeaking;

        // Auto-stop timer: Time.time at which IsSpeaking should be cleared after audio ends
        private float  _speakingEndTime = float.MaxValue;

        // Cumulative sample count and start time for current utterance (streaming mode).
        // Needed so _speakingEndTime is based on total pushed audio, not per-chunk.
        private int    _pushedSampleCount = 0;
        private float  _utteranceStartTime = 0f;

        // Rate-limiter: A2F frames must not be consumed faster than the configured output FPS.
        // At high Unity frame rates (e.g. 120 fps) with A2F at 30 fps, consuming one frame
        // per Update() would replay 4 s of animation in just 1 s.
        private float  _nextFrameTime = 0f;

        // Whether new weights arrived since last Apply
        private bool   _hasNewWeights;

        // ── Option B: A2F-driven autonomous emotion inference ────────
        // Inferred from ARKit blendshape weights so AvatarController can drive
        // body emotion in sync with A2F's neural lip sync output.
        // Updated every time ApplyToMesh() writes new weights.
        private string _estimatedEmotion         = "neutral";
        private float  _estimatedEmotionStrength = 0f;

        // ── Properties ───────────────────────────────────────────────

        /// <summary>True if the native plugin was created and validated successfully.</summary>
        public bool IsReady => _pluginReady;

        /// <summary>True while A2F is actively generating blendshape data.</summary>
        public bool IsSpeaking => _isSpeaking;

        /// <summary>
        /// Emotion inferred from current A2F blendshape weights.
        /// Updated each frame in ApplyToMesh(); valid while IsSpeaking == true.
        /// Values: "neutral", "joy", "sorrow", "surprise".
        /// </summary>
        public string EstimatedEmotion => _estimatedEmotion;

        /// <summary>0..1 confidence of EstimatedEmotion (0 when neutral).</summary>
        public float EstimatedEmotionStrength => _estimatedEmotionStrength;

        // ── ARKit 52 → Unity blendshape index lookup table ───────────
        // Maps ARKit shape index (0..51) to a Unity blendshape index.
        // -1 means "not mapped to this avatar".
        private int[] _arkitToUnityIndex;

        // ── Lifecycle ────────────────────────────────────────────────

        private void Awake()
        {
            _weightsBuf    = new float[kArKitCount];
            _smoothWeights = new float[kArKitCount];
            _targetWeights = new float[kArKitCount];
            _arkitToUnityIndex = new int[kArKitCount];
            for (int i = 0; i < kArKitCount; i++) _arkitToUnityIndex[i] = -1;
        }

        private void OnEnable()
        {
            if (_pluginReady) return;

            if (string.IsNullOrEmpty(_modelJsonPath))
            {
                Debug.LogWarning("[A2FLipSync] ModelJsonPath is empty — plugin disabled.");
                return;
            }

            // Resolve the actual model JSON path, handling v3.0 multi-character format.
            string resolvedPath = ResolveModelJsonPath(_modelJsonPath);
            if (string.IsNullOrEmpty(resolvedPath))
                return;

            try
            {
                _handle = Audio2FacePlugin.A2FPlugin_Create(
                    resolvedPath,
                    _useGpuSolver ? 1 : 0,
                    _frameRateNum,
                    _frameRateDen);

                if (_handle == IntPtr.Zero)
                {
                    Debug.LogError("[A2FLipSync] A2FPlugin_Create returned null handle.");
                    return;
                }

                if (Audio2FacePlugin.A2FPlugin_IsValid(_handle) == 0)
                {
                    string err = Audio2FacePlugin.A2FPlugin_GetLastError(_handle);
                    Debug.LogError($"[A2FLipSync] Plugin not valid after create: {err}");
                    Audio2FacePlugin.A2FPlugin_Destroy(_handle);
                    _handle = IntPtr.Zero;
                    return;
                }

                _pluginReady = true;
                Debug.Log($"[A2FLipSync] Plugin ready. WeightCount="
                         + $"{Audio2FacePlugin.A2FPlugin_GetWeightCount(_handle)}");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[A2FLipSync] Exception during init:\n{ex}\n"
                              + "Ensure A2FPlugin.dll and audio2x.dll are in Assets/Plugins/x86_64/ "
                              + "and TensorRT/CUDA DLLs are on PATH.");
            }
        }

        private void OnDisable()
        {
            if (_handle != IntPtr.Zero)
            {
                Audio2FacePlugin.A2FPlugin_Destroy(_handle);
                _handle = IntPtr.Zero;
            }
            _pluginReady = false;
            _isSpeaking  = false;
        }

        // ── A2F v3.0 multi-character model.json resolution ────────────────────

        // Character names matching v3.0 model.json arrays (Claire=0, James=1, Mark=2).
        private static readonly string[] s_V3CharNames = { "Claire", "James", "Mark" };

        /// <summary>
        /// Resolves the plugin model JSON path, handling the A2F v3.0 multi-character format.
        ///
        /// v2.x model.json uses "modelConfigPath" (singular string).
        /// v3.0 model.json uses "modelConfigPaths" (array) with separate entries for Claire/James/Mark.
        /// When a v3.0 path is detected, this method generates (or reuses) a per-character
        /// single-entry model.json in the same folder as the source, then returns its path.
        /// </summary>
        private string ResolveModelJsonPath(string jsonPath)
        {
            if (!System.IO.File.Exists(jsonPath))
            {
                Debug.LogError($"[A2FLipSync] model.json not found: {jsonPath}");
                return null;
            }

            string json;
            try
            {
                json = System.IO.File.ReadAllText(jsonPath);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[A2FLipSync] Cannot read model.json: {ex.Message}");
                return null;
            }

            // v3.0 detection: contains "modelConfigPaths" (plural array field).
            if (!json.Contains("\"modelConfigPaths\""))
                return jsonPath;  // v2.x single-char — use as-is

            // v3.0 multi-char: generate a per-character model.json.
            int charIdx = Mathf.Clamp(_characterIndex, 0, s_V3CharNames.Length - 1);
            string charName = s_V3CharNames[charIdx];
            string dir = System.IO.Path.GetDirectoryName(jsonPath);
            string outPath = System.IO.Path.Combine(dir, $"model_{charName.ToLower()}.json");

            if (!System.IO.File.Exists(outPath))
            {
                string charJson =
                    "{\n" +
                    "  \"networkInfoPath\": \"network_info.json\",\n" +
                    "  \"networkPath\": \"network.trt\",\n" +
                    $"  \"modelConfigPaths\": [\"model_config_{charName}.json\"],\n" +
                    $"  \"modelDataPaths\": [\"model_data_{charName}.npz\"],\n" +
                    "  \"blendshapePaths\": [{\n" +
                    $"    \"skin\":   {{\"config\": \"bs_skin_config_{charName}.json\",   \"data\": \"bs_skin_{charName}.npz\"}},\n" +
                    $"    \"tongue\": {{\"config\": \"bs_tongue_config_{charName}.json\", \"data\": \"bs_tongue_{charName}.npz\"}}\n" +
                    "  }]\n" +
                    "}";
                try
                {
                    System.IO.File.WriteAllText(outPath, charJson);
                    Debug.Log($"[A2FLipSync] Generated v3.0 per-char model.json → {outPath}");
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[A2FLipSync] Cannot write per-char model.json: {ex.Message}");
                    return null;
                }
            }

            Debug.Log($"[A2FLipSync] v3.0 resolved: character={charName} path={outPath}");
            return outPath;
        }

        private void Update()
        {
            if (!_pluginReady) return;

            // If frames are ready, process them — but no faster than the configured output FPS.
            // Without this guard, Unity running at e.g. 120 fps would consume all 30-fps A2F
            // frames in 1/4 of real time, making the lip animation finish before audio ends.
            int framesReady = Audio2FacePlugin.A2FPlugin_HasFrameReady(_handle);
            if (framesReady > 0 && Time.time >= _nextFrameTime)
            {
                int rc = Audio2FacePlugin.A2FPlugin_ProcessFrame(_handle);
                if (rc != 0)
                {
                    string err = Audio2FacePlugin.A2FPlugin_GetLastError(_handle);
                    Debug.LogWarning($"[A2FLipSync] ProcessFrame error {rc}: {err}");
                }
                // Advance the gate to the next expected frame wall-clock time.
                _nextFrameTime = Time.time + (float)_frameRateDen / _frameRateNum;
            }
            else if (_isSpeaking)
            {
                // Throttled log: only every ~60 frames to avoid spam
                if (Time.frameCount % 60 == 0)
                    Debug.Log($"[A2FLipSync] HasFrameReady=0 (waiting for model...)");
            }

            // Auto-stop: if audio duration has elapsed, clear speaking flag so LateUpdate
            // calls FadeToZero and the mouth returns to rest naturally.
            if (_isSpeaking && Time.time > _speakingEndTime)
            {
                _isSpeaking    = false;
                _hasNewWeights = false;
            }

            // Consume latest weights (if any).
            long tsUs = 0;
            int n = Audio2FacePlugin.A2FPlugin_GetLatestWeights(
                _handle, _weightsBuf, kArKitCount, out tsUs);
            if (n > 0)
            {
                _hasNewWeights = true;
                Debug.Log($"[A2FLipSync] Got weights: n={n} jaw={_weightsBuf[24]:F3} ts={tsUs}us");
            }
        }

        // ── Public API ───────────────────────────────────────────────

        /// <summary>
        /// Build the ARKit-to-Unity index mapping from AvatarController's Inspector values.
        /// Called once by AvatarController.Start() after Inspector values are set.
        /// </summary>
        public void SetIndexMap(
            int jawOpen,
            int mouthFunnel, int mouthPucker,
            int mouthLeft,   int mouthRight,
            int mouthRollUpper, int mouthRollLower,
            int mouthShrugUpper, int mouthShrugLower,
            int mouthClose,
            int mouthSmileL, int mouthSmileR,
            int mouthFrownL, int mouthFrownR,
            int mouthLowerDownL, int mouthLowerDownR,
            int mouthStretchL,  int mouthStretchR)
        {
            // Cache public properties (for AvatarController direct use)
            JawOpenIndex         = jawOpen;
            MouthFunnelIndex     = mouthFunnel;
            MouthPuckerIndex     = mouthPucker;
            MouthLeftIndex       = mouthLeft;
            MouthRightIndex      = mouthRight;
            MouthRollUpperIndex  = mouthRollUpper;
            MouthRollLowerIndex  = mouthRollLower;
            MouthShrugUpperIndex = mouthShrugUpper;
            MouthShrugLowerIndex = mouthShrugLower;
            MouthCloseIndex      = mouthClose;
            MouthSmileLIndex     = mouthSmileL;
            MouthSmileRIndex     = mouthSmileR;
            MouthFrownLIndex     = mouthFrownL;
            MouthFrownRIndex     = mouthFrownR;
            MouthLowerDownLIndex = mouthLowerDownL;
            MouthLowerDownRIndex = mouthLowerDownR;
            MouthStretchLIndex   = mouthStretchL;
            MouthStretchRIndex   = mouthStretchR;

            // Build lookup table: ARKit index → Unity blendshape index
            // Standard ARKit 52 order (alphabetical):
            // 0:browDownLeft 1:browDownRight 2:browInnerUp 3:browOuterUpLeft 4:browOuterUpRight
            // 5:cheekPuff 6:cheekSquintLeft 7:cheekSquintRight
            // 8:eyeBlinkLeft 9:eyeBlinkRight 10:eyeLookDownLeft 11:eyeLookDownRight
            // 12:eyeLookInLeft 13:eyeLookInRight 14:eyeLookOutLeft 15:eyeLookOutRight
            // 16:eyeLookUpLeft 17:eyeLookUpRight 18:eyeSquintLeft 19:eyeSquintRight
            // 20:eyeWideLeft 21:eyeWideRight
            // 22:jawForward 23:jawLeft 24:jawOpen 25:jawRight
            // 26:mouthClose 27:mouthDimpleLeft 28:mouthDimpleRight
            // 29:mouthFrownLeft 30:mouthFrownRight 31:mouthFunnel
            // 32:mouthLeft 33:mouthLowerDownLeft 34:mouthLowerDownRight
            // 35:mouthPressLeft 36:mouthPressRight 37:mouthPucker
            // 38:mouthRight 39:mouthRollLower 40:mouthRollUpper
            // 41:mouthShrugLower 42:mouthShrugUpper
            // 43:mouthSmileLeft 44:mouthSmileRight
            // 45:mouthStretchLeft 46:mouthStretchRight
            // 47:mouthUpperUpLeft 48:mouthUpperUpRight
            // 49:noseSneerLeft 50:noseSneerRight 51:tongueOut

            _arkitToUnityIndex[24] = jawOpen;
            _arkitToUnityIndex[31] = mouthFunnel;
            _arkitToUnityIndex[37] = mouthPucker;
            _arkitToUnityIndex[32] = mouthLeft;
            _arkitToUnityIndex[38] = mouthRight;
            _arkitToUnityIndex[40] = mouthRollUpper;
            _arkitToUnityIndex[39] = mouthRollLower;
            _arkitToUnityIndex[42] = mouthShrugUpper;
            _arkitToUnityIndex[41] = mouthShrugLower;
            _arkitToUnityIndex[26] = mouthClose;
            _arkitToUnityIndex[43] = mouthSmileL;
            _arkitToUnityIndex[44] = mouthSmileR;
            _arkitToUnityIndex[29] = mouthFrownL;
            _arkitToUnityIndex[30] = mouthFrownR;
            _arkitToUnityIndex[33] = mouthLowerDownL;
            _arkitToUnityIndex[34] = mouthLowerDownR;
            _arkitToUnityIndex[45] = mouthStretchL;
            _arkitToUnityIndex[46] = mouthStretchR;
        }

        /// <summary>
        /// Register vowel blendshape indices so A2F weights are additionally
        /// remapped to the same vowel shapes used by TTS phoneme lip sync.
        /// Call once from AvatarController.Start() after SetIndexMap().
        /// </summary>
        public void SetVowelMap(int a, int i, int u, int e, int o)
        {
            VowelAIndex = a;
            VowelIIndex = i;
            VowelUIndex = u;
            VowelEIndex = e;
            VowelOIndex = o;
            Debug.Log($"[A2FLipSync] VowelMap wired. A={a} I={i} U={u} E={e} O={o}");
        }

        /// <summary>
        /// Push a complete TTS utterance (16 kHz mono float32 PCM).
        /// After calling this, A2F will process frames incrementally in Update().
        /// Call Reset() before the next utterance.
        /// </summary>
        public void ProcessAudio(float[] pcm16kHz)
        {
            if (!_pluginReady || pcm16kHz == null || pcm16kHz.Length == 0) return;

            // Reset state from any previous utterance.
            Audio2FacePlugin.A2FPlugin_Reset(_handle);

            // Push all audio and signal end-of-stream.
            int rc = Audio2FacePlugin.A2FPlugin_PushAudio(_handle, pcm16kHz, pcm16kHz.Length);
            if (rc != 0)
            {
                Debug.LogWarning($"[A2FLipSync] PushAudio error {rc}: "
                                + Audio2FacePlugin.A2FPlugin_GetLastError(_handle));
                return;
            }
            rc = Audio2FacePlugin.A2FPlugin_CloseAudio(_handle);
            if (rc != 0)
            {
                Debug.LogWarning($"[A2FLipSync] CloseAudio error {rc}: "
                                + Audio2FacePlugin.A2FPlugin_GetLastError(_handle));
                return;
            }

            _isSpeaking    = true;
            _hasNewWeights = false;
            _nextFrameTime = 0f;  // allow first frame immediately on new utterance
            // Set auto-stop time: audio duration + 0.5s buffer for A2F processing lag
            _speakingEndTime = Time.time + pcm16kHz.Length / 16000f + 0.5f;
            Debug.Log($"[A2FLipSync] Audio pushed. samples={pcm16kHz.Length} "
                    + $"({pcm16kHz.Length / 16000f:F2}s) endTime={_speakingEndTime:F1}");
        }

        /// <summary>
        /// Push a chunk of streaming audio (no Close — use for real-time).
        /// Pair with <see cref="CloseStream"/> when the utterance ends.
        /// </summary>
        /// <param name="pcm16kHz">Float32 PCM at 16 kHz.</param>
        /// <param name="isFirst">True for the first chunk of a new utterance (resets plugin state).</param>
        public void PushAudioChunk(float[] pcm16kHz, bool isFirst = false)
        {
            if (!_pluginReady || pcm16kHz == null || pcm16kHz.Length == 0) return;
            if (isFirst)
            {
                Audio2FacePlugin.A2FPlugin_Reset(_handle);
                _nextFrameTime      = 0f;   // allow first frame immediately
                _pushedSampleCount  = 0;
                _utteranceStartTime = Time.time;
                _speakingEndTime    = 0f;
            }
            Audio2FacePlugin.A2FPlugin_PushAudio(_handle, pcm16kHz, pcm16kHz.Length);
            _pushedSampleCount += pcm16kHz.Length;
            _isSpeaking = true;
            // Deadline = utterance start + cumulative pushed duration + 0.5s buffer.
            // Using cumulative samples (not per-chunk) ensures batched streaming
            // (all chunks in one frame) gets the correct total audio deadline.
            _speakingEndTime = _utteranceStartTime + (float)_pushedSampleCount / 16000f + 0.5f;
        }

        /// <summary>Close the streaming audio accumulator for the current utterance.</summary>
        public void CloseStream()
        {
            if (!_pluginReady) return;
            Audio2FacePlugin.A2FPlugin_CloseAudio(_handle);
        }

        /// <summary>
        /// Apply current A2F blendshape weights to the given SkinnedMeshRenderer.
        /// Also updates EstimatedEmotion from the resulting smooth weights.
        /// Call every frame from AvatarController.Update() when A2F is active.
        /// </summary>
        public void ApplyToMesh(SkinnedMeshRenderer faceMesh)
        {
            if (faceMesh == null || !_pluginReady) return;

            float t = Time.deltaTime * _smoothSpeed;

            // Always update _smoothWeights for ALL ARKit indices (not just mapped ones)
            // so vowel remapping can read smooth values for any source ARKit shape.
            for (int arkitIdx = 0; arkitIdx < kArKitCount; arkitIdx++)
            {
                // Target: A2F weight (0..1) × globalStrength → Unity (0..100)
                // Hold last target when no new data so interpolation doesn't snap to zero
                // during inter-frame gaps (60fps Unity vs ~30fps A2F output).
                if (_hasNewWeights)
                    _targetWeights[arkitIdx] = _weightsBuf[arkitIdx] * _globalStrength * 100f;

                _smoothWeights[arkitIdx] = Mathf.Lerp(_smoothWeights[arkitIdx], _targetWeights[arkitIdx], t);

                int unityIdx = _arkitToUnityIndex[arkitIdx];
                if (unityIdx >= 0)
                    faceMesh.SetBlendShapeWeight(unityIdx,
                        Mathf.Clamp(_smoothWeights[arkitIdx], 0f, 100f));
            }

            // Also drive VRM vowel blendshapes from ARKit source weights:
            //   jawOpen(24)           → あ (mouth wide open)
            //   mouthFunnel(31)       → お (round/funnel)
            //   mouthPucker(37)       → う (pucker/round-small)
            //   mouthSmile L/R avg    → い (horizontal stretch)
            //   mouthStretch L/R avg  → え (lateral stretch)
            if (VowelAIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelAIndex, Mathf.Clamp(_smoothWeights[24], 0f, 100f));
            if (VowelOIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelOIndex, Mathf.Clamp(_smoothWeights[31], 0f, 100f));
            if (VowelUIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelUIndex, Mathf.Clamp(_smoothWeights[37], 0f, 100f));
            if (VowelIIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelIIndex, Mathf.Clamp((_smoothWeights[43] + _smoothWeights[44]) * 0.5f, 0f, 100f));
            if (VowelEIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelEIndex, Mathf.Clamp((_smoothWeights[45] + _smoothWeights[46]) * 0.5f, 0f, 100f));

            // ── Option B: classify emotion from smooth ARKit weights ──
            // mouthSmile L/R (43,44) → joy; mouthFrown L/R (29,30) → sorrow; jawOpen (24) → surprise
            UpdateEstimatedEmotion();

            // Mark weights as consumed once applied
            _hasNewWeights = false;
        }

        /// <summary>
        /// Fade all A2F-driven blendshapes to zero (called when speech ends).
        /// </summary>
        public void FadeToZero(SkinnedMeshRenderer faceMesh)
        {
            if (faceMesh == null) return;
            float t = Time.deltaTime * _smoothSpeed;

            for (int arkitIdx = 0; arkitIdx < kArKitCount; arkitIdx++)
            {
                _smoothWeights[arkitIdx] = Mathf.Lerp(_smoothWeights[arkitIdx], 0f, t);

                int unityIdx = _arkitToUnityIndex[arkitIdx];
                if (unityIdx >= 0)
                    faceMesh.SetBlendShapeWeight(unityIdx,
                        Mathf.Clamp(_smoothWeights[arkitIdx], 0f, 100f));
            }

            // Fade vowel shapes in sync with ARKit shapes
            if (VowelAIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelAIndex, Mathf.Clamp(_smoothWeights[24], 0f, 100f));
            if (VowelOIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelOIndex, Mathf.Clamp(_smoothWeights[31], 0f, 100f));
            if (VowelUIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelUIndex, Mathf.Clamp(_smoothWeights[37], 0f, 100f));
            if (VowelIIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelIIndex, Mathf.Clamp((_smoothWeights[43] + _smoothWeights[44]) * 0.5f, 0f, 100f));
            if (VowelEIndex >= 0)
                faceMesh.SetBlendShapeWeight(VowelEIndex, Mathf.Clamp((_smoothWeights[45] + _smoothWeights[46]) * 0.5f, 0f, 100f));

            // If completely faded, mark as done
            if (_smoothWeights[24] < 0.1f)   // jawOpen as sentinel
                _isSpeaking = false;
        }

        /// <summary>Stop A2F processing and fade the avatar mouth to rest.</summary>
        public void StopSpeaking()
        {
            _isSpeaking              = false;
            _hasNewWeights           = false;
            _speakingEndTime         = float.MaxValue;
            _estimatedEmotion        = "neutral";
            _estimatedEmotionStrength = 0f;
        }

        // ── Private helpers ──────────────────────────────────────────

        /// <summary>
        /// Classify emotion from the current smooth ARKit weights.
        /// Called from ApplyToMesh() after every weight update.
        ///
        /// Mapping (thresholds tuned for QuQu VRM, adjust if avatar differs):
        ///   mouthSmile L/R avg > 0.25  AND > 2× frown → joy
        ///   mouthFrown L/R avg > 0.20  AND > 2× smile → sorrow
        ///   jawOpen > 0.45 (normalised 0-1 from 0-100 range) → surprise
        ///   Otherwise → neutral
        /// </summary>
        private void UpdateEstimatedEmotion()
        {
            // _smoothWeights are 0..100 scale; normalise to 0..1 for thresholds
            float smileAvg = (_smoothWeights[43] + _smoothWeights[44]) * 0.005f; // avg * 1/100
            float frownAvg = (_smoothWeights[29] + _smoothWeights[30]) * 0.005f;
            float jawOpen  = _smoothWeights[24] * 0.01f;

            if (smileAvg > 0.25f && smileAvg > frownAvg * 2f)
            {
                _estimatedEmotion         = "joy";
                _estimatedEmotionStrength = Mathf.Clamp01(smileAvg * 2f);
            }
            else if (frownAvg > 0.20f && frownAvg > smileAvg * 2f)
            {
                _estimatedEmotion         = "sorrow";
                _estimatedEmotionStrength = Mathf.Clamp01(frownAvg * 2f);
            }
            else if (jawOpen > 0.45f && smileAvg < 0.10f && frownAvg < 0.10f)
            {
                _estimatedEmotion         = "surprise";
                _estimatedEmotionStrength = Mathf.Clamp01((jawOpen - 0.45f) * 4f);
            }
            else
            {
                _estimatedEmotion         = "neutral";
                _estimatedEmotionStrength = 0f;
            }
        }
    }
}

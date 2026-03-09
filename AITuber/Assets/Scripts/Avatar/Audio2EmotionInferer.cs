// Audio2EmotionInferer.cs
// Unity Sentis (com.unity.ai.inference) wrapper for audio2emotion-v2.2 ONNX inference.
// Accumulates 16 kHz float32 PCM from a2f_chunk stream; at a2f_stream_close, runs ONNX
// inference on-device and applies the resulting 10-dim A2F emotion vector —
// replacing the Python orchestrator's send_a2e_emotion() round-trip over WebSocket.
//
// Post-processing mirrors orchestrator/audio2emotion.py: A2EInferer._post_process().
// Constants: EmotionContrast=1.0, EmotionStrength=0.6, LiveBlendCoef=0.7, MaxEmotions=6.
//
// SRS refs: FR-A2E-01
// Requires: com.unity.ai.inference 2.5.0+ (defined as UNITY_AI_INFERENCE_ENABLED via asmdef
//           versionDefines when the package is present; degrades gracefully when absent).

using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

#if UNITY_AI_INFERENCE_ENABLED
using Unity.InferenceEngine;
#endif

namespace AITuber.Avatar
{
    /// <summary>
    /// On-device Audio2Emotion inference via Unity Sentis (com.unity.ai.inference).
    /// Wire: AvatarController calls PushPcmChunk() per a2f_chunk, then InferAndApply() at a2f_stream_close.
    /// Degrades gracefully when the ONNX model file is absent or the package is not installed.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class Audio2EmotionInferer : MonoBehaviour
    {
        // ── Constants (mirrors audio2emotion.py) ─────────────────────────────

        private const int   MinBufferLen    = 5_000;   // < 0.3 s → skip (MIN_BUFFER_LEN)
        private const int   MaxBufferLen    = 60_000;  // 3.75 s hard cap
        private const int   OptBufferLen    = 30_000;  // 1.875 s optimal window
        private const float EmotionContrast = 1.0f;
        private const float EmotionStrength = 0.6f;
        private const float LiveBlendCoef   = 0.7f;
        private const int   MaxEmotions     = 6;
        private const float NeutralThreshold = 0.20f;

        // 6-class label order (matches _EMOTION_LABELS in audio2emotion.py)
        private static readonly string[] EmotionLabels = { "angry", "disgust", "fear", "happy", "neutral", "sad" };

        // A2F 10-dim slot assignments (matches _EMO2A2F): angry=1, disgust=3, fear=4, happy=6, neutral=ignored, sad=9
        // Index aligns with EmotionLabels above.
        private static readonly int[] EmotionToA2FSlot = { 1, 3, 4, 6, -1, 9 };

        // ── Inspector ────────────────────────────────────────────────────────

        [Header("Audio2Emotion ONNX Model")]
        [Tooltip("Path to network.onnx.\n"
               + "• Relative path  → resolved from Application.streamingAssetsPath\n"
               + "• Absolute path  → used as-is\n"
               + "Default: 'audio2emotion-v2.2/network.onnx' under StreamingAssets/")]
        [SerializeField] private string _modelPath = "audio2emotion-v2.2/network.onnx";

        [Tooltip("Log inference label and timing to the Console.")]
        [SerializeField] private bool _debugLog;

        // ── Internal state ───────────────────────────────────────────────────

        // PCM accumulation buffer (16 kHz mono float32)
        private readonly List<float> _pcmBuf  = new List<float>(OptBufferLen);

        // Temporal-smoothing state (matches Python _prev_emo)
        private readonly float[]     _prevA2F = new float[10];

        private bool _isReady;

#if UNITY_AI_INFERENCE_ENABLED
        private Model  _model;
        private Worker _worker;
#endif

        // ── Properties ───────────────────────────────────────────────────────

        /// <summary>True when the ONNX model loaded successfully and Sentis is available.</summary>
        public bool IsReady => _isReady;

        // ── Lifecycle ────────────────────────────────────────────────────────

        private void OnEnable()
        {
#if UNITY_AI_INFERENCE_ENABLED
            string resolvedPath = ResolvePath(_modelPath);
            if (resolvedPath == null) return;           // warning already logged

            try
            {
                _model  = ModelLoader.Load(resolvedPath);
                _worker = new Worker(_model, BackendType.CPU);
                _isReady = true;
                Debug.Log($"[A2EInferer] Unity Sentis A2E ready. Model: {resolvedPath}");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[A2EInferer] Failed to load Sentis model '{resolvedPath}': {ex.Message}");
            }
#else
            // Package com.unity.ai.inference is not installed – silently skip.
            Debug.Log("[A2EInferer] com.unity.ai.inference package absent – Sentis A2E disabled (Python fallback active).");
#endif
        }

        private void OnDisable()
        {
#if UNITY_AI_INFERENCE_ENABLED
            _worker?.Dispose();
            _worker = null;
            _model  = null;
#endif
            _isReady = false;
        }

        // ── Public API ───────────────────────────────────────────────────────

        /// <summary>
        /// Accumulate a chunk of 16 kHz float32 PCM for the current utterance.
        /// Called by AvatarController for each a2f_chunk message (after base64 decode).
        /// Pass isFirst=true on the first chunk to reset the buffer and smoothing state.
        /// </summary>
        public void PushPcmChunk(float[] pcm16k, bool isFirst)
        {
            if (!_isReady) return;

            if (isFirst)
            {
                _pcmBuf.Clear();
                Array.Clear(_prevA2F, 0, _prevA2F.Length);
            }

            // Ring-cap at MaxBufferLen to bound memory (matches Python's ring-cap logic)
            int space = MaxBufferLen - _pcmBuf.Count;
            int take  = Math.Min(pcm16k.Length, space);
            for (int i = 0; i < take; i++)
                _pcmBuf.Add(pcm16k[i]);
        }

        /// <summary>
        /// Decode base64 PCM from an a2f_chunk WS message and push to the emotion buffer.
        /// No-op when not ready. Moved from AvatarController.FeedA2EChunk() (Issue #52). FR-A2E-01
        /// </summary>
        public void FeedA2FChunk(A2fChunkParams p)
        {
            if (!_isReady) return;
            if (p == null || string.IsNullOrEmpty(p.pcm_b64)) return;

            byte[] bytes;
            try   { bytes = Convert.FromBase64String(p.pcm_b64); }
            catch { return; }

            float[] pcm;
            if (string.Equals(p.format, "int16", StringComparison.OrdinalIgnoreCase))
            {
                int n = bytes.Length / 2;
                pcm = new float[n];
                for (int i = 0; i < n; i++)
                {
                    short s = (short)(bytes[i * 2] | (bytes[i * 2 + 1] << 8));
                    pcm[i] = s / 32768f;
                }
            }
            else
            {
                int n = bytes.Length / 4;
                pcm = new float[n];
                Buffer.BlockCopy(bytes, 0, pcm, 0, n * 4);
            }

            PushPcmChunk(pcm, p.is_first);
        }

        /// <summary>
        /// Run ONNX inference on the accumulated PCM and drive EmotionController + A2G scale.
        /// Called by AvatarController on a2f_stream_close.
        /// No-op if buffer is too short or model is not ready.
        /// </summary>
        public void InferAndApply(EmotionController emotion, Audio2GestureController a2gGesture)
        {
            if (!_isReady) return;

            if (_pcmBuf.Count < MinBufferLen)
            {
                if (_debugLog)
                    Debug.Log($"[A2EInferer] Buffer too short ({_pcmBuf.Count} < {MinBufferLen}), skipping inference.");
                return;
            }

#if UNITY_AI_INFERENCE_ENABLED
            // Use at most OptBufferLen from the tail (most recent speech)
            int start = Math.Max(0, _pcmBuf.Count - OptBufferLen);
            int len   = _pcmBuf.Count - start;
            float[] pcm = new float[len];
            _pcmBuf.CopyTo(start, pcm, 0, len);

            try
            {
                float inferStart = Time.realtimeSinceStartup;

                using var inputTensor  = new Tensor<float>(new TensorShape(1, len), pcm);
                _worker.Schedule(inputTensor);
                using var outputTensor = (Tensor<float>)_worker.PeekOutput();

                // Model outputs 6 logits: angry/disgust/fear/happy/neutral/sad
                // DownloadToArray() blocks until GPU work completes and downloads to CPU.
                float[] logitsArr = outputTensor.DownloadToArray();

                var (scores10, label) = PostProcess(logitsArr);

                if (_debugLog)
                    Debug.Log($"[A2EInferer] label={label} scores=[{string.Join(",", scores10)}] " +
                              $"t={(Time.realtimeSinceStartup - inferStart) * 1000f:F1}ms");

                emotion?.ApplyA2E(scores10);

                if (a2gGesture != null)
                {
                    float scale = label switch
                    {
                        "happy"   => 1.2f,
                        "angry"   => 1.0f,
                        "fear"    => 0.8f,
                        "disgust" => 0.7f,
                        "sad"     => 0.4f,
                        _         => 0.7f,
                    };
                    a2gGesture.SetEmotionGestureScale(scale);
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[A2EInferer] Sentis inference error: {ex.Message}");
            }
#endif
        }

        // ── Post-processing ──────────────────────────────────────────────────
        // Mirrors audio2emotion.py A2EInferer._post_process() exactly.

        private (float[] scores10, string label) PostProcess(float[] logits)
        {
            // Raw softmax for dominant-label detection
            float[] rawProbs = Softmax(logits);
            string  label    = DominantLabel(rawProbs);

            // EmotionContrast + softmax
            float[] vec = new float[logits.Length];
            for (int i = 0; i < logits.Length; i++) vec[i] = logits[i] * EmotionContrast;
            vec = Softmax(vec);

            // Zero neutral class at index 4
            vec[4] = 0f;

            // Keep top-MaxEmotions only (zero the rest)
            // Sort indices ascending by score; zero the bottom (Length - MaxEmotions) entries
            int[] idx = new int[vec.Length];
            for (int i = 0; i < idx.Length; i++) idx[i] = i;
            Array.Sort(idx, (a, b) => vec[a].CompareTo(vec[b]));   // ascending
            for (int k = 0; k < idx.Length - MaxEmotions; k++) vec[idx[k]] = 0f;

            // Map 6-class vec → 10-dim A2F vector
            float[] a2f = new float[10];
            for (int i = 0; i < EmotionToA2FSlot.Length; i++)
            {
                int slot = EmotionToA2FSlot[i];
                if (slot >= 0) a2f[slot] = vec[i];
            }

            // Temporal smoothing (matches Python: a2f = (1 - coef) * a2f + coef * prev)
            for (int i = 0; i < 10; i++)
                a2f[i] = (1f - LiveBlendCoef) * a2f[i] + LiveBlendCoef * _prevA2F[i];
            Array.Copy(a2f, _prevA2F, 10);

            // EmotionStrength scale
            for (int i = 0; i < 10; i++) a2f[i] *= EmotionStrength;

            return (a2f, label);
        }

        private static float[] Softmax(float[] x)
        {
            float max = x[0];
            for (int i = 1; i < x.Length; i++) if (x[i] > max) max = x[i];
            float sum = 0f;
            float[] e = new float[x.Length];
            for (int i = 0; i < x.Length; i++) { e[i] = MathF.Exp(x[i] - max); sum += e[i]; }
            for (int i = 0; i < x.Length; i++) e[i] /= sum;
            return e;
        }

        private static string DominantLabel(float[] probs)
        {
            int best = 0;
            for (int i = 1; i < probs.Length; i++) if (probs[i] > probs[best]) best = i;
            // If the best class is neutral (index 4), or confidence below threshold → "neutral"
            return (best == 4 || probs[best] < NeutralThreshold) ? "neutral" : EmotionLabels[best];
        }

        // ── Helpers ──────────────────────────────────────────────────────────

        private static string ResolvePath(string path)
        {
            if (Path.IsPathRooted(path))
            {
                if (File.Exists(path)) return path;
                Debug.LogWarning($"[A2EInferer] Absolute model path not found: {path}");
                return null;
            }

            string streamingPath = Path.Combine(Application.streamingAssetsPath, path);
            if (File.Exists(streamingPath)) return streamingPath;

            Debug.LogWarning($"[A2EInferer] ONNX model not found at '{streamingPath}'. "
                           + "Copy network.onnx from audio2emotion-v2.2 SDK to StreamingAssets/ "
                           + "or set an absolute path in the Inspector. Sentis A2E disabled.");
            return null;
        }
    }
}

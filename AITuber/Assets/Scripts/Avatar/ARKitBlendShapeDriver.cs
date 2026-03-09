// ARKitBlendShapeDriver.cs
// Drives 18 ARKit mouth blendshapes from jp_basic_8 phoneme profiles.
// Extracted from LipSyncController.cs (Issue #52, Phase 4 split).
//
// SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02

using System;
using System.Collections.Generic;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Drives 18 ARKit PerfectSync mouth blendshapes from jp_basic_8 phoneme profiles.
    /// Attach to the same GameObject as LipSyncController; auto-wired in LipSyncController.Awake().
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class ARKitBlendShapeDriver : MonoBehaviour
    {
        // ── SerializedFields ─────────────────────────────────────────

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
        [Range(0f, 1f), Tooltip("Master strength for ARKit-driven phoneme shapes. 0=off\u3001 1=full.")]
        [SerializeField] private float _articulationStrength = 0.85f;

        // ── Public index accessors (for Audio2FaceLipSync.SetIndexMap) ──

        public int JawOpen         => _jawOpenIndex;
        public int MouthFunnel     => _mouthFunnelIndex;
        public int MouthPucker     => _mouthPuckerIndex;
        public int MouthLeft       => _mouthLeftIndex;
        public int MouthRight      => _mouthRightIndex;
        public int MouthRollUpper  => _mouthRollUpperIndex;
        public int MouthRollLower  => _mouthRollLowerIndex;
        public int MouthShrugUpper => _mouthShrugUpperIndex;
        public int MouthShrugLower => _mouthShrugLowerIndex;
        public int MouthClose      => _mouthCloseIndex;
        public int MouthSmileL     => _mouthSmileLIndex;
        public int MouthSmileR     => _mouthSmileRIndex;
        public int MouthFrownL     => _mouthFrownLIndex;
        public int MouthFrownR     => _mouthFrownRIndex;
        public int MouthLowerDownL => _mouthLowerDownLIndex;
        public int MouthLowerDownR => _mouthLowerDownRIndex;
        public int MouthStretchL   => _mouthStretchLIndex;
        public int MouthStretchR   => _mouthStretchRIndex;

        // ── ARKit phoneme profiles ────────────────────────────────────

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
        // Tuned for QuQu avatar (jawOpen=#78 etc.). Adjust _articulationStrength in
        // the Inspector to scale all shapes globally without editing these.
        private static readonly Dictionary<string, ARKitWeights> s_Profiles =
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
                // \u3046: rounded / puckered
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

        // ── Per-shape lerp state (no allocations) ───────────────────────────

        private SkinnedMeshRenderer _faceMesh;
        private float _crossfadeMs = 60f;

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

        // ── Initialization ────────────────────────────────────────────

        /// <summary>Set face mesh and auto-detect ARKit indices from blendshape names.</summary>
        public void Initialize(SkinnedMeshRenderer mesh)
        {
            _faceMesh = mesh;
            if (mesh != null && mesh.sharedMesh != null && _jawOpenIndex < 0)
                AutoDetect(mesh);
        }

        /// <summary>Update crossfade timing to match LipSyncController viseme crossfade.</summary>
        public void SetCrossfadeMs(float ms) => _crossfadeMs = ms;

        // ── Drive methods ─────────────────────────────────────────────

        /// <summary>
        /// Apply blended ARKit phoneme weights from two visemes with coarticulation blend.
        /// visemeStrength: overall viseme multiplier (0..1); _articulationStrength is applied internally.
        /// </summary>
        public void Apply(string v1, float w1, string v2, float w2, float visemeStrength)
        {
            if (_faceMesh == null) return;
            if (!s_Profiles.TryGetValue(v1, out var p1)) p1 = default;
            if (!s_Profiles.TryGetValue(v2, out var p2)) p2 = default;
            const float kScale = 100f;
            float s = visemeStrength * _articulationStrength * kScale;
            float t = Time.deltaTime / Mathf.Max(_crossfadeMs / 1000f, 0.01f);
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

        /// <summary>Lerp all ARKit shapes toward zero (called when not speaking).</summary>
        public void FadeToZero()
        {
            if (_faceMesh == null) return;
            float t = Time.deltaTime / Mathf.Max(_crossfadeMs / 1000f, 0.01f);
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

        /// <summary>Instantly zero all lerp-state floats (for avatar_reset).</summary>
        public void ResetState()
        {
            _curJawOpen = _curMouthFunnel = _curMouthPucker = 0f;
            _curMouthLeft = _curMouthRight = 0f;
            _curMouthRollUpper = _curMouthRollLower = 0f;
            _curMouthShrugUpper = _curMouthShrugLower = 0f;
            _curMouthClose = 0f;
            _curMouthSmileL = _curMouthSmileR = 0f;
            _curMouthFrownL = _curMouthFrownR = 0f;
            _curMouthLowerDownL = _curMouthLowerDownR = 0f;
            _curMouthStretchL = _curMouthStretchR = 0f;
            FadeToZero();
        }

        private void LerpARKit(int index, ref float current, float target, float t)
        {
            if (index < 0 || _faceMesh == null) return;
            current = Mathf.Lerp(current, target, t);
            _faceMesh.SetBlendShapeWeight(index, Mathf.Clamp(current, 0f, 100f));
        }

        // ── ARKit index helpers ───────────────────────────────────────

        /// <summary>Auto-detect ARKit indices from blendshape names on the mesh.</summary>
        public void AutoDetect(SkinnedMeshRenderer mesh)
        {
            if (mesh == null || mesh.sharedMesh == null) return;
            var smesh = mesh.sharedMesh;
            int count = smesh.blendShapeCount;

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

            int found = 0;
            for (int i = 0; i < count; i++)
            {
                string shapeName = smesh.GetBlendShapeName(i);
                if (map.TryGetValue(shapeName, out var setter))      { setter(i); found++; continue; }
                if (aliases.TryGetValue(shapeName, out var setter2)) { setter2(i); found++; }
            }
            Debug.Log($"[ARKitDriver] Auto-detect: jawOpen={_jawOpenIndex} mouthSmileL={_mouthSmileLIndex} ({found} shapes matched on '{mesh.name}')");
        }

        /// <summary>Right-click in Inspector to auto-fill indices for the QuQu avatar.</summary>
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
            Debug.Log("[ARKitDriver] ARKit indices auto-configured for QuQu avatar.");
#if UNITY_EDITOR
            UnityEditor.EditorUtility.SetDirty(this);
#endif
        }
    }
}

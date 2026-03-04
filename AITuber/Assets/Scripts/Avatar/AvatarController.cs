// AvatarController.cs
// Thin renderer: applies avatar_update / avatar_event / avatar_viseme
// commands received via WebSocket to the VRM/Live2D avatar.
//
// SRS refs: FR-A7-01, FR-LIPSYNC-01, FR-LIPSYNC-02
// Hard rules: No business logic. No allocations in hot path.

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using AITuber.Room;
using AITuber.Growth;

namespace AITuber.Avatar
{
    /// <summary>
    /// Applies avatar commands from AvatarWSClient to the scene.
    /// Attach to the same GameObject as AvatarWSClient, or wire via Inspector.
    /// </summary>
    public class AvatarController : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private AvatarWSClient _wsClient;
        [SerializeField] private SkinnedMeshRenderer _faceMesh;
        [SerializeField] private Animator _animator;

        [Header("IK / Look Target")]
        [SerializeField] private Transform _lookAtCamera;
        [SerializeField] private Transform _lookAtChat;
        [SerializeField] private Transform _lookAtDown;
        [SerializeField] private float _lookAtWeight = 0.8f;
        private Transform _currentLookAtTarget;

        [Header("Comment Gaze")]
        [Tooltip("コメント読み上げ中に視線を向けるオブジェクト。AITuber/Setup Comment Area で自動配置できます。")]
        [SerializeField] private Transform _commentAreaAnchor;
        [Header("Blend Shape Indices (set in Inspector)")]
        [Tooltip("BlendShape index for mouth open (ParamMouthOpenY)")]
        [SerializeField] private int _mouthOpenBlendIndex = -1;
        [Tooltip("BlendShape index for joy/happy expression")]
        [SerializeField] private int _joyBlendIndex = -1;
        [Tooltip("BlendShape index for angry expression")]
        [SerializeField] private int _angryBlendIndex = -1;
        [Tooltip("BlendShape index for sorrow/sad expression")]
        [SerializeField] private int _sorrowBlendIndex = -1;
        [Tooltip("BlendShape index for surprised expression")]
        [SerializeField] private int _surprisedBlendIndex = -1;
        [Tooltip("BlendShape index for thinking expression")]
        [SerializeField] private int _thinkingBlendIndex = -1;
        [Tooltip("BlendShape index for eye close / blink (Fcl_EYE_Close)")]
        [SerializeField] private int _blinkBlendIndex = -1;
        [Header("Blink Settings")]
        [SerializeField] private float _blinkIntervalMin = 2.5f;
        [SerializeField] private float _blinkIntervalMax = 6.0f;
        [SerializeField] private float _blinkDuration = 0.12f;
        [Header("VRM Viseme Indices (jp_basic_8)")]
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

        [Header("State")]
        [SerializeField] private string _currentEmotion = "neutral";
        [SerializeField] private string _currentGesture = "none";
        [SerializeField] private string _currentLookTarget = "camera";

        // Lip sync state
        private float _targetMouthOpen;
        private float _currentMouthOpen;
        private const float MouthSmoothSpeed = 20f;

        // Random look target state
        private bool _isRandomLook;
        private float _nextRandomLookTime;
        private const float RandomLookIntervalMin = 1.5f;
        private const float RandomLookIntervalMax = 4.0f;

        // (A) Saccade – micro eye-movement for liveliness
        private Vector3 _saccadeOffset;
        private Vector3 _saccadeTargetOffset;
        private float   _saccadeTimer;

        // (C) Breathing animation
        private float     _breathPhase;
        private Transform _breathBone;

        // Comment read state
        private bool  _hasCommentGazeOverride;
        private float _commentHeadBlend;   // 0..1, lerps toward 1 on start, 0 on end

        // (B) Saved Inspector blink defaults – restored when emotion resets
        private float _defaultBlinkIntervalMin;
        private float _defaultBlinkIntervalMax;
        private float _defaultBlinkDuration;

        // Emotion blend state
        private float _targetEmotionWeight;
        private float _currentEmotionWeight;
        private int _activeEmotionBlendIndex = -1;
        private const float EmotionSmoothSpeed = 8f;

        // Config state
        private float _mouthSensitivity = 1f;
        private bool _blinkEnabled = true;
        private string _idleMotion = "default";

        // Gesture deduplication: only fire SetTrigger when gesture changes
        private string _lastAppliedGesture = "none";
        // State-tracking for dedup reset (gesture→Idle transition detection)
        private bool _wasInGestureState = false;

        // Viseme state (FR-LIPSYNC-02)
        private VisemeEvent[] _visemeEvents;
        private int _visemeIndex;
        private float _visemeStartTime;
        private bool _visemePlaying;
        private float _visemeCrossfadeMs = 60f;
        private float _visemeStrength = 1f;

        // Anticipation: mouth starts moving this many ms BEFORE the phoneme onset.
        // Physical jaw/lip movement is ~50ms slower than acoustic onset, so we
        // pre-empt the blend shape target change. (Animation best-practice: 1-2 frames)
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

        // ARKit PerfectSync current weights (per-shape lerp state, no allocations)
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

        // Auto-blink state
        private float _nextBlinkTime;
        private float _blinkPhase; // 0=idle, >0=blink in progress
        private bool _isBlinking;

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

        // ── Lifecycle ────────────────────────────────────────────────

        private void Awake()
        {
            // LookAt ターゲットと CommentArea を AvatarRoot の子にする。
            // AvatarGrounding が AvatarRoot を床に吸着させると子オブジェクトも追従するため、
            // ターゲットを World 座標で再設定する必要がなくなる。
            // worldPositionStays=true により現在のワールド位置は維持される。
            ReparentIfOrphan(_lookAtCamera);
            ReparentIfOrphan(_lookAtChat);
            ReparentIfOrphan(_lookAtDown);
            ReparentIfOrphan(_commentAreaAnchor);
        }

        private void ReparentIfOrphan(Transform t)
        {
            if (t != null && t.parent == null)
                t.SetParent(transform, worldPositionStays: true);
        }

        private void Start()
        {
            // AvatarAnimatorController を強制的に割り当てる。
            // VRC 等の既存コントローラが付いていても上書きする。
            if (_animator != null)
            {
                RuntimeAnimatorController ourCtrl = null;
                // 既に正しいコントローラが設定されていれば再利用
                if (_animator.runtimeAnimatorController != null
                    && _animator.runtimeAnimatorController.name == "AvatarAnimatorController")
                {
                    ourCtrl = _animator.runtimeAnimatorController;
                    Debug.Log($"[AvatarCtrl] Animator '{_animator.gameObject.name}' already uses AvatarAnimatorController.");
                }
                else
                {
                    // Resources 全体 + DescendantAssets から AvatarAnimatorController を探す
                    var allCtrl = Resources.FindObjectsOfTypeAll<RuntimeAnimatorController>();
                    foreach (var c in allCtrl)
                    {
                        if (c.name == "AvatarAnimatorController") { ourCtrl = c; break; }
                    }
                    if (ourCtrl != null)
                    {
                        var prev = _animator.runtimeAnimatorController?.name ?? "none";
                        _animator.runtimeAnimatorController = ourCtrl;
                        Debug.Log($"[AvatarCtrl] Replaced controller '{prev}' → 'AvatarAnimatorController' on '{_animator.gameObject.name}'");
                    }
                    else
                    {
                        Debug.LogError("[AvatarCtrl] AvatarAnimatorController not found! Gestures will not work.");
                    }
                }

                // Root motion を無効化（クリップ内の root curve がキャラを回転させるのを防ぐ）
                _animator.applyRootMotion = false;

                // AvatarAnimatorController 以外のコントローラを持つ Animator をすべて無効化。
                // VRC HandsLayer / SittingLayer 等がボーンを上書きするのを防ぐ。
                foreach (var a in GetComponentsInChildren<Animator>(true))
                {
                    if (a == _animator) continue;
                    bool isConflict = a.avatar != null
                        && (a.runtimeAnimatorController == null
                            || a.runtimeAnimatorController.name != "AvatarAnimatorController");
                    if (isConflict)
                    {
                        var ctrlName = a.runtimeAnimatorController?.name ?? "none";
                        a.enabled = false;
                        Debug.Log($"[AvatarCtrl] Disabled conflicting Animator on '{a.gameObject.name}' (controller='{ctrlName}')");
                    }
                }
                // 自分自身（AvatarRoot）の Animator も確認
                var selfAnim = GetComponent<Animator>();
                if (selfAnim != null && selfAnim != _animator && selfAnim.avatar != null
                    && (selfAnim.runtimeAnimatorController == null
                        || selfAnim.runtimeAnimatorController.name != "AvatarAnimatorController"))
                {
                    var ctrlName = selfAnim.runtimeAnimatorController?.name ?? "none";
                    selfAnim.enabled = false;
                    Debug.Log($"[AvatarCtrl] Disabled conflicting self-Animator on '{selfAnim.gameObject.name}' (controller='{ctrlName}')");
                }

                // デフォルトモーションを IdleAlt に設定。
                // AnimatorController の defaultState が IdleAlt になっていれば自動で遷移するが、
                // 旧バージョンのコントローラとの互換性のため 1 フレーム後に Play() でも確定させる。
                // FR-A7-01: アイドル状態は IdleAlt (自然な立ちポーズ) を使用する。
                StartCoroutine(PlayInitialIdleAlt());
            }
        }

        /// <summary>
        /// PlayMode 開始直後に IdleAlt ステートへ遷移させる。
        /// Animator が完全に初期化されるまで 1 フレーム待つ必要があるため Coroutine で実装。
        /// </summary>
        private IEnumerator PlayInitialIdleAlt()
        {
            // Animator が完全に初期化されるまで待つ（最大 30 フレーム = 約 0.5 秒）
            int safety = 30;
            while (_animator != null && !_animator.isInitialized && safety-- > 0)
                yield return null;
            yield return null; // 初期化直後のフレームをさらに 1 つスキップ
            if (_animator != null)
            {
                _animator.Play("IdleAlt", 0, 0f);
                _currentGesture      = "idle_alt";
                _lastAppliedGesture  = "idle_alt";
                Debug.Log("[AvatarCtrl] Initial motion set to IdleAlt.");
            }
        }

        private void OnEnable()
        {
            if (_wsClient != null)
            {
                _wsClient.OnMessageReceived += HandleMessage;
            }
            // Save Inspector blink defaults so emotion-linked changes can restore them
            _defaultBlinkIntervalMin = _blinkIntervalMin;
            _defaultBlinkIntervalMax = _blinkIntervalMax;
            _defaultBlinkDuration    = _blinkDuration;
            ScheduleNextBlink();
            // Initialize LookAt target from the Inspector default ("camera")
            // so _currentLookAtTarget is never null even before the first avatar_update.
            ApplyLookTarget(_currentLookTarget);
        }

        private void OnDisable()
        {
            if (_wsClient != null)
            {
                _wsClient.OnMessageReceived -= HandleMessage;
            }
        }

        private float _animDiagTimer;

        private void Update()
        {
            // Smooth mouth open (FR-LIPSYNC-01: RMS lip sync at 30Hz)
            _currentMouthOpen = Mathf.Lerp(
                _currentMouthOpen, _targetMouthOpen,
                Time.deltaTime * MouthSmoothSpeed);

            // Apply viseme timeline if playing (FR-LIPSYNC-02)
            if (_visemePlaying && _visemeEvents != null)
            {
                UpdateViseme();
            }
            else
            {
                // Fade ARKit PerfectSync shapes to zero when not speaking
                FadeARKitToZero();
            }

            // Smooth emotion blend transitions
            UpdateEmotionBlend();

            // (A) Saccade – micro eye jitter for liveliness
            UpdateSaccade();

            // Auto-blink
            if (_blinkEnabled)
                UpdateBlink();

            // Apply to blend shape
            // During viseme playback the native vowel shapes (あいうえお) already
            // include the correct jaw/lip position. Driving jawOpen on top of them
            // causes the mouth to open far too wide, so we suppress it here.
            if (!_visemePlaying)
                ApplyMouthOpen(_currentMouthOpen);
            else
                ApplyMouthOpen(0f); // fade jawOpen to closed while viseme is active

            // ── Gesture→Idle 遷移検出: dedup tracker リセット ──
            // ジェスチャー再生完了後に同一ジェスチャーが再度発動できるよう、
            // non-loop(ジェスチャー) → loop(Idle) への状態遷移を毎フレーム監視
            if (_animator != null)
            {
                bool inGesture = !_animator.GetCurrentAnimatorStateInfo(0).loop;
                if (_wasInGestureState && !inGesture && _lastAppliedGesture != "none")
                {
                    Debug.Log($"[AvatarCtrl] Gesture '{_lastAppliedGesture}' finished → resetting dedup tracker");
                    _lastAppliedGesture = "none";
                }
                _wasInGestureState = inGesture;
            }

            // ── Animator ステート診断（1秒毎）──
            _animDiagTimer -= Time.deltaTime;
            if (_animDiagTimer <= 0f && _animator != null)
            {
                _animDiagTimer = 1f;
                var info = _animator.GetCurrentAnimatorStateInfo(0);
                // 右上腕ボーンの実際の回転を確認
                var rightArm = _animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
                string boneInfo = rightArm != null
                    ? $" RightUpperArm.localRot={rightArm.localEulerAngles}"
                    : " RightUpperArm=null";
                Debug.Log($"[AvatarCtrl] AnimState: '{_animator.GetCurrentAnimatorClipInfo(0).Length}clips' " +
                          $"normalizedTime={info.normalizedTime:F2} loop={info.loop} " +
                          $"speed={_animator.speed} enabled={_animator.enabled} applyRoot={_animator.applyRootMotion}" +
                          boneInfo);
            }
        }

        // ── Message handling ─────────────────────────────────────────

        private void HandleMessage(AvatarMessage msg, object typedParams)
        {
            // Never crash on unknown commands (backward compatible)
            switch (msg.cmd)
            {
                case "avatar_update":
                    HandleUpdate(typedParams as AvatarUpdateParams);
                    break;
                case "avatar_event":
                    HandleEvent(typedParams as AvatarEventParams);
                    break;
                case "avatar_config":
                    HandleConfig(typedParams as AvatarConfigParams);
                    break;
                case "avatar_reset":
                    HandleReset();
                    break;
                case "avatar_viseme":
                    HandleViseme(typedParams as AvatarVisemeParams);
                    break;
                case "capabilities":
                    HandleCapabilities(typedParams as CapabilitiesParams);
                    break;
                case "room_change":
                    HandleRoomChange(typedParams as RoomChangeParams);
                    break;
                case "avatar_intent":
                    HandleIntent(typedParams as AvatarIntentParams);
                    break;
                default:
                    // Unknown command: ignore (protocol: backward compatible)
                    Debug.Log($"[AvatarCtrl] Ignoring unknown cmd: {msg.cmd}");
                    break;
            }
        }

        // ── avatar_intent (Growth System) ──────────────────────────────

        private void HandleIntent(AvatarIntentParams p)
        {
            if (p == null) return;
            var dispatcher = AITuber.Growth.ActionDispatcher.Instance;
            if (dispatcher != null)
                dispatcher.Dispatch(p, _currentGesture);
            else
                Debug.LogWarning("[AvatarCtrl] avatar_intent received but ActionDispatcher.Instance is null.");
        }

        // ── Growth System hooks (called by ActionDispatcher) ──────────────

        /// <summary>
        /// Applies individual avatar_update fields from a BehaviorPolicy entry.
        /// Null or empty arguments are treated as "no change" (keeps current value).
        /// </summary>
        public void ApplyFromPolicy(string emotion, string gesture, string lookTarget)
        {
            bool changed = false;
            if (!string.IsNullOrEmpty(emotion)    && emotion    != _currentEmotion)
            { _currentEmotion    = emotion;    ApplyEmotion(emotion);         changed = true; }
            if (!string.IsNullOrEmpty(gesture)    && gesture    != _currentGesture)
            { _currentGesture    = gesture;    ApplyGesture(gesture);         changed = true; }
            if (!string.IsNullOrEmpty(lookTarget) && lookTarget != _currentLookTarget)
            { _currentLookTarget = lookTarget; ApplyLookTarget(lookTarget);   changed = true; }
            if (changed)
                Debug.Log($"[AvatarCtrl] ApplyFromPolicy: emotion={_currentEmotion} gesture={_currentGesture} look={_currentLookTarget}");
        }

        /// <summary>
        /// Fires an avatar_event from a BehaviorPolicy entry.
        /// </summary>
        public void TriggerEventFromPolicy(string eventName, float intensity)
        {
            if (string.IsNullOrEmpty(eventName)) return;
            HandleEvent(new AvatarEventParams { @event = eventName, intensity = intensity });
        }

        /// <summary>
        /// Test / integration-test entry point: feeds a pre-parsed message directly
        /// without going through the WebSocket client.
        /// </summary>
        public void HandleMessageForTest(AvatarMessage msg, object typedParams)
        {
            if (msg == null) return;
            HandleMessage(msg, typedParams);
        }

        /// <summary>
        /// Parse a raw JSON string and route to the appropriate handler.
        /// Convenience overload for integration tests and external callers.
        /// </summary>
        public void HandleMessage(string json)
        {
            var (msg, typed) = AvatarMessageParser.Parse(json);
            if (msg == null) return;
            HandleMessage(msg, typed);
        }

        // ── avatar_update ────────────────────────────────────────────

        private void HandleUpdate(AvatarUpdateParams p)
        {
            if (p == null) return;

            _currentEmotion = p.emotion ?? "neutral";
            _currentGesture = p.gesture ?? "none";
            _currentLookTarget = p.look_target ?? "camera";
            _targetMouthOpen = Mathf.Clamp01(p.mouth_open);

            // Map emotion → VRM BlendShapePreset
            ApplyEmotion(_currentEmotion);

            // Map gesture → Animation trigger
            ApplyGesture(_currentGesture);

            // Map look_target → IK target
            ApplyLookTarget(_currentLookTarget);
        }

        // ── avatar_event ─────────────────────────────────────────────

        private void HandleEvent(AvatarEventParams p)
        {
            if (p == null) return;

            string eventName = p.@event;
            float intensity = Mathf.Clamp01(p.intensity);

            switch (eventName)
            {
                case "comment_read_start":
                    Debug.Log($"[AvatarCtrl] Comment read start (intensity={intensity})");
                    _hasCommentGazeOverride = true;
                    break;
                case "comment_read_end":
                    Debug.Log($"[AvatarCtrl] Comment read end");
                    _hasCommentGazeOverride = false;
                    break;
                case "topic_switch":
                    Debug.Log($"[AvatarCtrl] Topic switch");
                    break;
                case "break_start":
                    Debug.Log("[AvatarCtrl] Break start");
                    if (_animator != null)
                        _animator.SetBool("IsIdle", true);
                    break;
                case "break_end":
                    Debug.Log("[AvatarCtrl] Break end");
                    if (_animator != null)
                        _animator.SetBool("IsIdle", false);
                    break;
                default:
                    // Unknown event: ignore
                    break;
            }
        }

        // ── avatar_config ────────────────────────────────────────────

        private void HandleConfig(AvatarConfigParams p)
        {
            if (p == null) return;
            _mouthSensitivity = Mathf.Clamp(p.mouth_sensitivity, 0.1f, 5f);
            _blinkEnabled = p.blink_enabled;
            _idleMotion = p.idle_motion ?? "default";
            if (_animator != null)
            {
                _animator.SetBool("BlinkEnabled", _blinkEnabled);
                _animator.SetFloat("IdleMotionIndex", _idleMotion == "energetic" ? 1f : 0f);
            }
            Debug.Log($"[AvatarCtrl] Config: sensitivity={_mouthSensitivity}, " +
                      $"blink={_blinkEnabled}, idle={_idleMotion}");
        }

        // ── capabilities (optional handshake) ────────────────────────

        private void HandleCapabilities(CapabilitiesParams p)
        {
            if (p == null) return;
            Debug.Log($"[AvatarCtrl] Capabilities: mouth_open={p.mouth_open}, " +
                      $"viseme={p.viseme}, viseme_set=[{(p.viseme_set != null ? string.Join(",", p.viseme_set) : "")}]");
            // Future: enable/disable features based on orchestrator capabilities
        }

        // ── room_change (FR-ROOM-02) ──────────────────────────────────

        private void HandleRoomChange(RoomChangeParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.room_id)) return;
            if (RoomManager.Instance != null)
                RoomManager.Instance.SwitchRoom(p.room_id);
            else
                Debug.LogWarning("[AvatarCtrl] room_change received but RoomManager not found.");
        }

        // ── avatar_reset ─────────────────────────────────────────────

        private void HandleReset()
        {
            _currentEmotion = "neutral";
            _currentGesture = "none";
            _currentLookTarget = "camera";
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
            FadeARKitToZero(); // apply to blend shapes immediately
            Debug.Log("[AvatarCtrl] Reset to neutral");
        }

        // ── avatar_viseme (FR-LIPSYNC-02) ────────────────────────────

        private void HandleViseme(AvatarVisemeParams p)
        {
            if (p == null || p.events == null || p.events.Length == 0)
            {
                Debug.LogWarning($"[AvatarCtrl] HandleViseme: null or empty events (p={p})");
                return;
            }
            Debug.Log($"[AvatarCtrl] Viseme: {p.events.Length} events, faceMesh={((_faceMesh != null) ? _faceMesh.name : "NULL")}, AIdx={_visemeAIndex}");

            // Events must be sorted by t_ms (TC-A7-07)
            // They should arrive sorted, but verify defensively.
            Array.Sort(p.events, (a, b) => a.t_ms.CompareTo(b.t_ms));

            _visemeEvents = p.events;
            _visemeIndex = 0;
            _visemeStartTime = Time.time;
            _visemePlaying = true;
            _visemeCrossfadeMs = Mathf.Clamp(p.crossfade_ms, 40f, 80f);
            _visemeStrength = Mathf.Clamp01(p.strength);
        }

        private void UpdateViseme()
        {
            float elapsed_ms = (Time.time - _visemeStartTime) * 1000f;

            // ── Anticipation: advance index when we are VisemeAnticipationMs ahead ──
            // This makes the mouth START moving before the phoneme is heard,
            // matching physical jaw motion latency (~50ms).
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
            // When we are past CoarticulationStart fraction through the current phoneme,
            // we interpolate blend-shape targets toward the next phoneme shape.
            // This gives the overlapping, anticipatory lip shapes seen in natural speech.
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
                    // smoothstep for natural ease-in / ease-out of coarticulation
                    float raw = Mathf.Clamp01((progress - CoarticulationStart)
                                              / (1f - CoarticulationStart));
                    coBlend = raw * raw * (3f - 2f * raw); // smoothstep
                    nextViseme = _visemeEvents[_visemeIndex + 1].v;
                }
            }

            // ── Compute final per-vowel target weights (current + next blend) ──
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

            // ARKit PerfectSync: blend profiles for current + next viseme (Coarticulation-aware)
            ApplyARKitWeights(
                currentViseme, 1f - coBlend,
                nextViseme,    coBlend,
                _visemeStrength * _articulationStrength);

            // jawOpen (legacy RMS guard: keep _targetMouthOpen updated so it fades
            // smoothly when viseme ends. ARKit jawOpen is driven above for configured avatars.)
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
                    // ARKit shapes will fade via the FadeARKitToZero() path in Update
                }
            }
        }

        /// <summary>
        /// Returns normalised (0..1) per-vowel contributions for the given viseme,
        /// pre-scaled by <paramref name="strength"/>.
        /// </summary>
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

        /// <summary>
        /// Drive the five VRM vowel blend shapes directly from normalised weights (0..1).
        /// Crossfade is applied via LerpVisemeWeight each frame.
        /// </summary>
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

        /// <summary>
        /// Drive individual VRM vowel blend shapes (A/I/U/E/O) with crossfade.
        /// Legacy helper used by reset/silence paths — delegates to ApplyVisemeWeightsDirect.
        /// </summary>
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

        // ── ARKit PerfectSync drive ──────────────────────────────────

        /// <summary>
        /// Blend two ARKit phoneme profiles and drive all configured mouth blend shapes.
        /// Weights w1+w2 should sum to \u22641 (coarticulation). globalStr applies on top.
        /// </summary>
        private void ApplyARKitWeights(string v1, float w1, string v2, float w2, float globalStr)
        {
            if (_faceMesh == null) return;
            if (!s_ArkitProfiles.TryGetValue(v1, out var p1)) p1 = default;
            if (!s_ArkitProfiles.TryGetValue(v2, out var p2)) p2 = default;
            const float kScale = 100f; // normalised 0..1 \u2192 Unity blend-shape 0..100
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

        /// <summary>Smooth-fade all ARKit shapes to 0 (called every frame when not speaking).</summary>
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
            Debug.Log("[AvatarCtrl] ARKit indices auto-configured for QuQu avatar.");
#if UNITY_EDITOR
            UnityEditor.EditorUtility.SetDirty(this);
#endif
        }

        /// <summary>
        /// Map jp_basic_8 viseme to mouth_open value.
        /// Viseme set: sil, a, i, u, e, o, m, fv
        /// </summary>
        private static float VisemeToMouthOpen(string viseme)
        {
            return viseme switch
            {
                "sil" => 0.0f,
                "a" => 0.5f,
                "i" => 0.2f,
                "u" => 0.25f,
                "e" => 0.3f,
                "o" => 0.4f,
                "m" => 0.05f,
                "fv" => 0.1f,
                _ => 0.0f, // Unknown viseme: safe default
            };
        }

        // ── Blend shape application ──────────────────────────────────

        private void ApplyMouthOpen(float value)
        {
            if (_faceMesh == null || _mouthOpenBlendIndex < 0)
                return;

            // Blend shapes are 0..100 in Unity; apply mouth_sensitivity
            _faceMesh.SetBlendShapeWeight(
                _mouthOpenBlendIndex,
                Mathf.Clamp(value * _mouthSensitivity * 100f, 0f, 100f));
        }

        // ── Emotion → VRM BlendShape mapping ────────────────────────

        private void ApplyEmotion(string emotion)
        {
            // Reset previous emotion blend
            if (_activeEmotionBlendIndex >= 0 && _faceMesh != null)
                _faceMesh.SetBlendShapeWeight(_activeEmotionBlendIndex, 0f);

            _activeEmotionBlendIndex = emotion switch
            {
                "happy" => _joyBlendIndex,
                "angry" => _angryBlendIndex,
                "sad" => _sorrowBlendIndex,
                "surprised" or "panic" => _surprisedBlendIndex,
                "thinking" => _thinkingBlendIndex,
                _ => -1, // neutral: no emotion blend
            };

            _targetEmotionWeight = (_activeEmotionBlendIndex >= 0) ? 100f : 0f;

            // (B) Emotion-linked blink behaviour
            switch (emotion)
            {
                case "surprised":
                case "panic":
                    // Wide-eyed stare: pause blinking for ~5 seconds
                    _isBlinking    = false;
                    _blinkDuration = _defaultBlinkDuration;
                    _nextBlinkTime = Time.time + 5f;
                    break;
                case "happy":
                    // Lively: tighter blink interval
                    _blinkIntervalMin = Mathf.Min(_defaultBlinkIntervalMin, 1.5f);
                    _blinkIntervalMax = Mathf.Min(_defaultBlinkIntervalMax, 3.0f);
                    _blinkDuration    = _defaultBlinkDuration;
                    break;
                case "sad":
                    // Heavy lids: slower, longer blinks
                    _blinkIntervalMin = 4.0f;
                    _blinkIntervalMax = 8.0f;
                    _blinkDuration    = 0.20f;
                    break;
                default:
                    // Restore Inspector defaults
                    _blinkIntervalMin = _defaultBlinkIntervalMin;
                    _blinkIntervalMax = _defaultBlinkIntervalMax;
                    _blinkDuration    = _defaultBlinkDuration;
                    break;
            }
        }

        private void UpdateEmotionBlend()
        {
            // Smooth emotion transitions
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

        // ── Auto-blink ──────────────────────────────────────────────

        private void ScheduleNextBlink()
        {
            _nextBlinkTime = Time.time + UnityEngine.Random.Range(_blinkIntervalMin, _blinkIntervalMax);
            _isBlinking = false;
            _blinkPhase = 0f;
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

        // ── Gesture → Animation trigger ──────────────────────────────

        private void ApplyGesture(string gesture)
        {
            if (_animator == null)
            {
                Debug.LogWarning("[AvatarCtrl] ApplyGesture: _animator is NULL");
                return;
            }
            // gesture="none" → reset dedup tracker so next non-none gesture fires
            if (gesture == "none")
            {
                _lastAppliedGesture = "none";
                return;
            }

            // Deduplicate: only fire trigger on gesture change to prevent
            // rapid-repeat loops when Orchestrator sends the same gesture
            // in consecutive avatar_update messages.
            if (gesture == _lastAppliedGesture) return;
            _lastAppliedGesture = gesture;

            // Map gesture names to Animator triggers
            // Trigger names match AnimationGenerator.cs AddOrUpdateGestureState()
            string trigger = gesture switch
            {
                // ── 既存ジェスチャー ──
                "nod"           => "Nod",
                "shake"         => "Shake",
                "wave"          => "Wave",
                "cheer"         => "Cheer",
                "shrug"         => "Shrug",
                "facepalm"      => "Facepalm",

                // ── 感情・リアクション系 ──
                "shy"           => "Shy",
                "laugh"         => "Laugh",
                "surprised"     => "Surprised",
                "rejected"      => "Rejected",
                "sigh"          => "Sigh",
                "thankful"      => "Thankful",

                // ── 悲しみ系 ──
                "sad_idle"      => "SadIdle",
                "sad_kick"      => "SadKick",

                // ── 思考系 ──
                "thinking"      => "Thinking",

                // ── 代替アイドル ──
                "idle_alt"      => "IdleAlt",

                // ── 座り系 ──
                "sit_down"      => "SitDown",
                "sit_idle"      => "SitIdle",
                "sit_laugh"     => "SitLaugh",
                "sit_clap"      => "SitClap",
                "sit_point"     => "SitPoint",
                "sit_disbelief" => "SitDisbelief",
                "sit_kick"      => "SitKick",

                // ── M4: スタンドアップ追加ジェスチャー ──
                "bow"           => "Bow",
                "clap"          => "Clap",
                "thumbs_up"     => "ThumbsUp",
                "point_forward" => "PointForward",
                "spin"          => "Spin",

                // ── M19: 日常生活 Sims-like (FR-LIFE-01) ──
                "walk"          => "Walk",
                "sit_read"      => "SitRead",
                "sit_eat"       => "SitEat",
                "sit_write"     => "SitWrite",
                "sleep_idle"    => "SleepIdle",
                "stretch"       => "Stretch",

                _               => null,
            };

            if (trigger != null)
            {
                Debug.Log($"[AvatarCtrl] SetTrigger: gesture='{gesture}' → trigger='{trigger}'");
                _animator.SetTrigger(trigger);
                // Wave時はフレーム毎ボーン診断を起動
                if (gesture == "wave")
                    StartCoroutine(DiagnoseWaveBone());
            }
            else
            {
                Debug.LogWarning($"[AvatarCtrl] Unknown gesture: '{gesture}'");
            }
        }

        private IEnumerator DiagnoseWaveBone()
        {
            var rightArm  = _animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
            var rightHand = _animator.GetBoneTransform(HumanBodyBones.RightHand);
            float elapsed = 0f;
            int frame = 0;
            while (elapsed < 2f)
            {
                yield return null;
                elapsed += Time.deltaTime;
                frame++;
                if (frame % 10 == 0) // 10フレームごと
                {
                    var stateInfo = _animator.GetCurrentAnimatorStateInfo(0);
                    string armRot  = rightArm  != null ? rightArm.localEulerAngles.ToString("F1") : "null";
                    string handRot = rightHand != null ? rightHand.localEulerAngles.ToString("F1") : "null";
                    Debug.Log($"[Wave診断] t={elapsed:F2}s frame={frame} state=loop:{stateInfo.loop} nTime={stateInfo.normalizedTime:F2} " +
                              $"RightUpperArm={armRot} RightHand={handRot}");
                }
            }
        }

        // ── LookTarget → IK ─────────────────────────────────────────

        private void ApplyLookTarget(string target)
        {
            _isRandomLook = target == "random";
            if (_isRandomLook)
            {
                // 初回はすぐに切り替え
                _nextRandomLookTime = 0f;
                PickRandomLookTarget();
                return;
            }
            _currentLookAtTarget = target switch
            {
                "camera" => _lookAtCamera,
                "chat" => _lookAtChat,
                "down" => _lookAtDown,
                "center" => _lookAtCamera,
                _ => _lookAtCamera,
            };
        }

        private void PickRandomLookTarget()
        {
            var targets = new[] { _lookAtCamera, _lookAtChat, _lookAtDown };
            _currentLookAtTarget = targets[UnityEngine.Random.Range(0, targets.Length)];
            _nextRandomLookTime = Time.time + UnityEngine.Random.Range(
                RandomLookIntervalMin, RandomLookIntervalMax);
        }

        private void OnAnimatorIK(int layerIndex) => ApplyLookAtIK();

        /// <summary>AvatarIKProxy から転送される IK コールバック。</summary>
        public void OnAnimatorIKFromProxy(int layerIndex) => ApplyLookAtIK();

        private void ApplyLookAtIK()
        {
            if (_animator == null) return;

            // random モード: 一定間隔でターゲットを切り替え
            if (_isRandomLook && Time.time >= _nextRandomLookTime)
                PickRandomLookTarget();

            // コメントスキャン中は _currentLookAtTarget が null でも動作させる。
            // null のときは _lookAtCamera にフォールバック。
            // _commentHeadBlend > 0 の間はフェードアウト中なのでカメラをフォールバックに使う
            bool commentActive = _hasCommentGazeOverride || _commentHeadBlend > 0.01f;
            Transform activeLookTarget = _currentLookAtTarget
                ?? (commentActive ? _lookAtCamera : null);

            if (activeLookTarget != null || commentActive)
            {
                // 頭部アニメーションを持つジェスチャー中は headWeight=0 にする。
                // Nod/Shake/Facepalm はアニメーションで頭を動かすため IK を切る。
                // 通常は headWeight を小さくして「視線主体・顔はほぼ動かない」にする。
                //   bodyWeight = 0   : 体回転なし（アニメーション優先）
                //   headWeight = 0.1 : 顔はごく僅かに追従
                //   eyesWeight = 1.0 : 眼球は最大追従
                //   clampWeight= 0.7 : 眼球の可動範囲を広げる
                bool headGesture = _currentGesture is "nod" or "shake" or "facepalm";
                // _commentHeadBlend: 0(通常) ↔ 1(コメントスキャン中)をなめらかにlerp。
                // start/end 時のガクつきを防ぐ。
                float blendTarget = _hasCommentGazeOverride ? 1f : 0f;
                _commentHeadBlend = Mathf.Lerp(_commentHeadBlend, blendTarget, Time.deltaTime * 8f);
                float headW  = headGesture ? 0f : Mathf.Lerp(0.1f,  0.65f, _commentHeadBlend);
                float bodyW  = Mathf.Lerp(0f,   0.12f, _commentHeadBlend);
                float clampW = Mathf.Lerp(0.8f, 0.9f,  _commentHeadBlend);
                _animator.SetLookAtWeight(_lookAtWeight, bodyW, headW, 1f, clampW);
                // end 時も gazePos → normalPos をなめらかにブレンド。
                // _commentAreaAnchor を直接読む（コルーチン不要）。
                Vector3 normalPos  = activeLookTarget != null ? activeLookTarget.position : transform.position + Vector3.forward;
                Vector3 commentPos = _commentAreaAnchor != null ? _commentAreaAnchor.position : normalPos;
                Vector3 gazePos    = Vector3.Lerp(normalPos, commentPos, _commentHeadBlend);
                _animator.SetLookAtPosition(gazePos + _saccadeOffset);
            }
            else
            {
                _animator.SetLookAtWeight(0f);
            }
        }

        // ── (A) Saccade \u2013 micro eye-movement for liveliness ─────────────

        private void UpdateSaccade()
        {
            _saccadeTimer -= Time.deltaTime;
            if (_saccadeTimer <= 0f)
            {
                const float r = 0.015f; // \u00b11.5 cm amplitude
                _saccadeTargetOffset = new Vector3(
                    UnityEngine.Random.Range(-r,        r),
                    UnityEngine.Random.Range(-r * 0.4f, r * 0.4f),
                    0f);
                _saccadeTimer = UnityEngine.Random.Range(0.15f, 0.40f);
            }
            // Fast lerp so saccades feel snappy but not teleporting
            _saccadeOffset = Vector3.Lerp(_saccadeOffset, _saccadeTargetOffset,
                                          Time.deltaTime * 18f);
        }

        // ── (C) Breathing animation ─────────────────────────────────

        private void LateUpdate()
        {
            if (_animator == null) return;
            _breathBone ??= _animator.GetBoneTransform(HumanBodyBones.Chest);
            if (_breathBone == null) return;

            const float cycle   = 4.0f;   // seconds per breath cycle
            const float degrees = 0.6f;   // \u00b10.6\u00b0 pitch on chest bone
            _breathPhase += Time.deltaTime * (Mathf.PI * 2f / cycle);
            float angle = Mathf.Sin(_breathPhase) * degrees;
            // Additive: applied on top of whatever the Animator set this frame
            _breathBone.localRotation *= Quaternion.Euler(angle, 0f, 0f);
        }

        // ── Public API ───────────────────────────────────────────────

        public string CurrentEmotion => _currentEmotion;
        public string CurrentGesture => _currentGesture;
        public string CurrentLookTarget => _currentLookTarget;
        public float CurrentMouthOpen => _currentMouthOpen;
    }
}

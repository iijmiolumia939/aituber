// AvatarController.cs
// Thin renderer: applies avatar_update / avatar_event / avatar_viseme
// commands received via WebSocket to the FBX (Humanoid) avatar.
// Note: UniVRM (com.vrmc.vrm) is kept in Packages/manifest.json for
//       VRMSpringBone hair-physics only, not for the avatar file format.
//
// SRS refs: FR-A7-01, FR-LIPSYNC-01, FR-LIPSYNC-02
// Hard rules: No business logic. No allocations in hot path.

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using AITuber.Room;
using AITuber.Growth;
using AITuber.Behavior;

namespace AITuber.Avatar
{
    /// <summary>
    /// Applies avatar commands from AvatarWSClient to the scene.
    /// Attach to the same GameObject as AvatarWSClient, or wire via Inspector.
    /// </summary>
    [RequireComponent(typeof(GestureController))]
    [RequireComponent(typeof(EmotionController))]
    [RequireComponent(typeof(GazeController))]
    [RequireComponent(typeof(LipSyncController))]
    public class AvatarController : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private AvatarWSClient _wsClient;
        [SerializeField] private SkinnedMeshRenderer _faceMesh;
        [SerializeField] private Animator _animator;

        [Header("Audio2Gesture Neural Body Gesture (optional, FR-GESTURE-AUTO-01)")]
        [Tooltip("Optional Audio2GestureController for upper-body neural gesture generation from audio. "
               + "When A2GPlugin.dll is absent, this component gracefully becomes a no-op.")]
        [SerializeField] private Audio2GestureController _a2gGesture;

        [Header("Audio2Emotion On-Device Inference (optional, FR-A2E-01)")]
        [Tooltip("Optional Audio2EmotionInferer for on-device Sentis A2E inference. "
               + "When the ONNX model is absent or the package is not installed, falls back to Python WS a2e_emotion.")]
        [SerializeField] private Audio2EmotionInferer _a2eInferer;

        [Header("State")]
        [SerializeField] private string _currentEmotion = "neutral";
        [SerializeField] private string _currentGesture = "none";
        [SerializeField] private string _currentLookTarget = "camera";

        // Gesture control – fields/logic owned by GestureController (Issue #52, Phase 1)
        private GestureController _gesture;

        // Emotion/blink control – fields/logic owned by EmotionController (Issue #52, Phase 2)
        private EmotionController _emotion;

        // Gaze/saccade control – fields/logic owned by GazeController (Issue #52, Phase 3)
        private GazeController _gaze;

        // Lip sync control – fields/logic owned by LipSyncController (Issue #52, Phase 4)
        private LipSyncController _lipSync;



        // ── Lifecycle ────────────────────────────────────────────────

        private void Awake()
        {
            _gesture   = GetComponent<GestureController>()     ?? gameObject.AddComponent<GestureController>();
            _emotion   = GetComponent<EmotionController>()    ?? gameObject.AddComponent<EmotionController>();
            _gaze      = GetComponent<GazeController>()       ?? gameObject.AddComponent<GazeController>();
            _lipSync   = GetComponent<LipSyncController>()    ?? gameObject.AddComponent<LipSyncController>();
            // Auto-detect Audio2EmotionInferer on the same GameObject (optional, FR-A2E-01)
            if (_a2eInferer == null)
                _a2eInferer = GetComponent<Audio2EmotionInferer>();
        }

        private void Start()
        {
            // Auto-wire Audio2GestureController (same GameObject, optional).
            if (_a2gGesture == null)
                _a2gGesture = GetComponent<Audio2GestureController>();
            _a2gGesture?.CaptureNeutralPose(_animator);
            _gaze.Initialize(_animator);

            // Auto-detect face SkinnedMeshRenderer: pick the one with the most blendshapes.
            if (_faceMesh == null)
            {
                SkinnedMeshRenderer best = null;
                int bestCount = 0;
                foreach (var smr in GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    int n = smr.sharedMesh != null ? smr.sharedMesh.blendShapeCount : 0;
                    if (n > bestCount) { bestCount = n; best = smr; }
                }
                _faceMesh = best;
                if (_faceMesh != null)
                    Debug.Log($"[AvatarCtrl] _faceMesh auto-detected: {_faceMesh.name} ({bestCount} blendshapes)");
                else
                    Debug.LogWarning("[AvatarCtrl] _faceMesh: no SkinnedMeshRenderer with blendshapes found in children.");
            }

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

                // FR-A7-01: GestureController.Start() plays IdleAlt once Animator is ready.
                // Eagerly reflect the initial gesture state so BSR IsBusy guard preserves it.
                _currentGesture = "idle_alt";
            }

            // FR-LIPSYNC-01: Initialize LipSyncController with face mesh (Issue #52, Phase 4)
            _lipSync.Initialize(_faceMesh);
        }

        private void OnEnable()
        {
            if (_wsClient != null)
            {
                _wsClient.OnMessageReceived += HandleMessage;
            }
            // Initialize LookAt target from the Inspector default ("camera")
            // so GazeController's target is set before the first avatar_update.
            _gaze.SetTarget(_currentLookTarget);
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
            // Delegate all lip sync logic to LipSyncController (Issue #52, Phase 4)
            _lipSync.DoUpdate();

            // Option B (FR-GESTURE-AUTO-01): A2F emotion feedback loop.
            // A2F's blendshape output implicitly encodes prosodic emotion (smile ↔ joy,
            // frown ↔ sorrow, jaw surprise). Read EstimatedEmotion and apply to avatar
            // autonomously – no LLM involvement needed during speech playback.
            if (_lipSync.IsA2FActive)
            {
                string a2fEmotion = _lipSync.EstimatedA2FEmotion;
                if (a2fEmotion != "neutral" && a2fEmotion != _currentEmotion)
                {
                    _currentEmotion = a2fEmotion;
                    _emotion.Apply(a2fEmotion);
                }
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
                    _lipSync.HandleViseme(typedParams as AvatarVisemeParams);
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
                case "appearance_update":
                    HandleAppearanceUpdate(typedParams as AppearanceUpdateParams);
                    break;
                case "behavior_start":
                    HandleBehaviorStart(typedParams as BehaviorStartParams);
                    break;
                case "a2f_audio":
                    _lipSync.HandleA2FAudio(typedParams as A2FAudioParams);
                    break;
                case "a2f_chunk":
                    _lipSync.HandleA2FChunk(typedParams as A2fChunkParams);
                    FeedA2EChunk(typedParams as A2fChunkParams);
                    break;
                case "a2f_stream_close":
                    _lipSync.HandleA2FStreamClose();
                    // FR-A2E-01: on-device Sentis inference (no-op when _a2eInferer is absent/not ready)
                    _a2eInferer?.InferAndApply(_emotion, _a2gGesture);
                    break;
                case "a2g_chunk":
                    HandleA2GChunk(typedParams as A2gChunkParams);
                    break;
                case "a2g_stream_close":
                    HandleA2GStreamClose(typedParams as A2gStreamCloseParams);
                    break;
                case "a2e_emotion":
                    HandleA2EEmotion(typedParams as A2EEmotionParams);
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

        // ── appearance_update (FR-SHADER-02, FR-APPEARANCE-01/02) ─────────────

        private void HandleAppearanceUpdate(AppearanceUpdateParams p)
        {
            if (p == null) return;
            var ctrl = AppearanceController.Instance;
            if (ctrl == null)
            {
                Debug.LogWarning("[AvatarCtrl] appearance_update received but AppearanceController.Instance is null.");
                return;
            }
            if (!string.IsNullOrEmpty(p.shader_mode))
            {
                if (System.Enum.TryParse<ShaderMode>(p.shader_mode, true, out var mode))
                    ctrl.ApplyShaderMode(mode);
                else
                    Debug.LogWarning($"[AvatarCtrl] Unknown shader_mode: '{p.shader_mode}'");
            }
            if (!string.IsNullOrEmpty(p.costume)) ctrl.ApplyCostume(p.costume);
            if (!string.IsNullOrEmpty(p.hair))    ctrl.ApplyHair(p.hair);
        }

        // ── Growth System hooks (called by ActionDispatcher) ──────────────

        /// <summary>
        /// Applies individual avatar_update fields from a BehaviorPolicy entry.
        /// Null or empty arguments are treated as "no change" (keeps current value).
        /// Delegates to ApplyAvatarState to avoid duplicating field-assignment logic. FR-WS-01
        /// </summary>
        public void ApplyFromPolicy(string emotion, string gesture, string lookTarget)
        {
            // null/empty means "keep current" – opposite of HandleUpdate's "reset to default"
            string e = string.IsNullOrEmpty(emotion)    ? _currentEmotion    : emotion;
            string g = string.IsNullOrEmpty(gesture)    ? _currentGesture    : gesture;
            string l = string.IsNullOrEmpty(lookTarget) ? _currentLookTarget : lookTarget;

            if (e == _currentEmotion && g == _currentGesture && l == _currentLookTarget) return;

            ApplyAvatarState(e, g, l, _lipSync.TargetMouthOpen); // mouth_open not part of policy → preserve
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

        /// <summary>
        /// Single authoritative setter: writes all three state fields and fires
        /// the corresponding Apply* calls. Both HandleUpdate and ApplyFromPolicy
        /// must resolve their null semantics before calling this. FR-WS-01
        /// </summary>
        private void ApplyAvatarState(string emotion, string gesture, string lookTarget, float mouthOpen)
        {
            _currentEmotion    = emotion;
            _currentGesture    = gesture;
            _currentLookTarget = lookTarget;
            _lipSync.SetMouthOpen(mouthOpen);
            _emotion.Apply(emotion);
            _gesture.Apply(gesture);
            _gaze.SetTarget(lookTarget);
            _gaze.SetHeadGestureActive(gesture is "nod" or "shake" or "facepalm");
        }

        /// <summary>
        /// BehaviorSequenceRunner 専用ジェスチャー適用口。
        /// HandleUpdate の IsBusy ガードを経由しないため、BSR 自身のアクション
        /// (walk / walk_stop / sit_write 等) が BSR の IsBusy フラグで弾かれない。
        /// Bug fix: FR-BEHAVIOR-SEQ-01 — SendAvatarUpdate was routing through HandleUpdate
        /// which locked gesture to _currentGesture whenever bsr.IsBusy == true, preventing
        /// the walk trigger from ever firing during a behavior sequence.
        /// </summary>
        public void ApplyBehaviorGesture(string gesture, string emotion, string lookTarget)
        {
            ApplyAvatarState(
                string.IsNullOrEmpty(emotion)    ? "neutral" : emotion,
                string.IsNullOrEmpty(gesture)    ? "none"    : gesture,
                string.IsNullOrEmpty(lookTarget) ? "camera"  : lookTarget,
                0f);
        }

        /// <summary>
        /// Resets the gesture dedup cache so the next identical trigger fires correctly.
        /// Call this whenever BSR cancels a behavior mid-execution (StopBehavior). FR-BEHAVIOR-SEQ-01
        /// </summary>
        public void ResetGestureDedup() => _gesture.ResetGestureDedup();

        private void HandleUpdate(AvatarUpdateParams p)
        {
            if (p == null) return;
            // null in avatar_update means "reset to default" (WS caller owns the full state)
            string gesture = p.gesture ?? "none";
            // When BehaviorSequenceRunner is executing, it owns gesture control.
            // Ignore any gesture override from the orchestrator's avatar_update
            // so walk → walk_stop → sit_write sequences play without interruption.
            // FR-BEHAVIOR-SEQ-01
            var bsr = BehaviorSequenceRunner.Instance;
            if (bsr != null && bsr.IsBusy)
                gesture = _currentGesture;
            ApplyAvatarState(
                p.emotion     ?? "neutral",
                gesture,
                p.look_target ?? "camera",
                p.mouth_open);
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
                    _gaze.SetCommentGazeOverride(true);
                    break;
                case "comment_read_end":
                    Debug.Log($"[AvatarCtrl] Comment read end");
                    _gaze.SetCommentGazeOverride(false);
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
            _lipSync.SetMouthSensitivity(Mathf.Clamp(p.mouth_sensitivity, 0.1f, 5f));
            _emotion.SetBlinkEnabled(p.blink_enabled);
            _gesture.SetIdleMotion(p.idle_motion ?? "default");
            if (_animator != null)
                _animator.SetBool("BlinkEnabled", p.blink_enabled);
            Debug.Log($"[AvatarCtrl] Config: sensitivity={Mathf.Clamp(p.mouth_sensitivity, 0.1f, 5f)}, " +
                      $"blink={p.blink_enabled}, idle={_gesture.IdleMotion}");
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

        // ── behavior_start (FR-BEHAVIOR-SEQ-01) ──────────────────────

        private void HandleBehaviorStart(BehaviorStartParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.behavior)) return;
            var runner = BehaviorSequenceRunner.Instance;
            if (runner != null)
                runner.StartBehavior(p.behavior);
            else
                Debug.LogWarning($"[AvatarCtrl] behavior_start: BehaviorSequenceRunner not found. behavior='{p.behavior}'");
        }

        // ── a2f_chunk / a2f_stream_close / a2f_audio
        // Delegated to LipSyncController (Issue #52, Phase 4)
        // Also feeds Audio2EmotionInferer (FR-A2E-01) for on-device Sentis inference.

        /// <summary>
        /// Decodes base64 PCM from the a2f_chunk params and feeds it to Audio2EmotionInferer.
        /// No-op when _a2eInferer is absent or not ready.
        /// Decode logic mirrors LipSyncController.HandleA2FChunk() — kept local to avoid coupling.
        /// </summary>
        private void FeedA2EChunk(A2fChunkParams p)
        {
            if (_a2eInferer == null || !_a2eInferer.IsReady) return;
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

            _a2eInferer.PushPcmChunk(pcm, p.is_first);
        }

        // ── a2g_chunk / a2g_stream_close (Option A: Audio2Gesture) ────────────
        // FR-GESTURE-AUTO-01: Stream audio to the A2G plugin so it generates
        // upper-body bone rotations in sync with the lip sync utterance.
        private void HandleA2GChunk(A2gChunkParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.pcm_b64)) return;
            if (_a2gGesture == null || !_a2gGesture.IsReady)  return;

            byte[] bytes;
            try   { bytes = System.Convert.FromBase64String(p.pcm_b64); }
            catch (Exception ex)
            {
                Debug.LogError($"[AvatarCtrl] a2g_chunk: base64 decode failed: {ex.Message}");
                return;
            }

            float[] pcm;
            if (string.Equals(p.format, "int16", System.StringComparison.OrdinalIgnoreCase))
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
                Buffer.BlockCopy(bytes, 0, pcm, 0, bytes.Length);
            }

            _a2gGesture.PushAudioChunk(pcm, p.is_first);
        }

        private void HandleA2GStreamClose(A2gStreamCloseParams p)
        {
            _a2gGesture?.CloseStream();
        }

        // ── a2e_emotion (FR-A2E-01) ──────────────────────────────────

        /// <summary>
        /// Handles the a2e_emotion command from the Python orchestrator.
        /// Applies the Audio2Emotion 10-dim vector to face blendshapes via EmotionController,
        /// and adjusts Audio2Gesture intensity proportional to the detected emotion.
        /// FR-A2E-01: emotion-driven face + gesture integration.
        /// </summary>
        private void HandleA2EEmotion(A2EEmotionParams p)
        {
            if (p == null) return;
            string label = string.IsNullOrEmpty(p.label) ? "neutral" : p.label;

            // Drive face blendshapes
            if (p.scores != null && p.scores.Length >= 10)
                _emotion.ApplyA2E(p.scores);

            // Adjust A2G gesture intensity based on emotion energy
            if (_a2gGesture != null)
            {
                float scale = label switch
                {
                    "happy"   => 1.2f,
                    "angry"   => 1.0f,
                    "fear"    => 0.8f,
                    "disgust" => 0.7f,
                    "sad"     => 0.4f,
                    _         => 0.7f,  // neutral / unknown
                };
                _a2gGesture.SetEmotionGestureScale(scale);
            }

            _currentEmotion = label;
        }

        // ── avatar_reset ─────────────────────────────────────────────

        private void HandleReset()
        {
            _currentEmotion = "neutral";
            _currentGesture = "none";
            _currentLookTarget = "camera";
            _gaze.SetTarget("camera");
            // Delegate all LipSync state reset to LipSyncController (Issue #52, Phase 4)
            _lipSync.HandleReset();
            Debug.Log("[AvatarCtrl] Reset to neutral");
        }

        /// <summary>AvatarIKProxy から転送される IK コールバック。
        /// AvatarController は AvatarRoot にアタッチされており Animator の GO ではないため
        /// OnAnimatorIK は直接呼ばれない。AvatarIKProxy がわりに転送する。</summary>
        public void OnAnimatorIKFromProxy(int layerIndex) => _gaze.OnAnimatorIKFromProxy(layerIndex);

        private void LateUpdate()
        {
            // Delegate A2F blendshape application to LipSyncController (Issue #52, Phase 4)
            _lipSync.DoLateUpdate();

            // Option A (FR-GESTURE-AUTO-01): Apply A2G bone rotations after Animator evaluation
            // so neural gesture does not fight with animation clip root poses.
            // Phase 4: pass current LookAt influence so A2G reduces Head/Neck weight
            // proportionally and avoids competing with the LookAt IK from OnAnimatorIK.
            if (_a2gGesture != null && _a2gGesture.IsReady && _animator != null)
            {
                _a2gGesture.SetLookAtInfluence(_gaze.LookAtInfluence);
                _a2gGesture.ApplyToRig(_animator);
            }
        }

        // ── Public API ───────────────────────────────────────────────

        public string CurrentEmotion => _currentEmotion;
        public string CurrentGesture => _currentGesture;
        public string CurrentLookTarget => _currentLookTarget;
        public float CurrentMouthOpen => _lipSync.CurrentMouthOpen;
    }
}

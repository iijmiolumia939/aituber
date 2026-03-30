// AvatarController.cs
// Thin renderer: applies avatar_update / avatar_event / avatar_viseme
// commands received via WebSocket to the FBX (Humanoid) avatar.
// Hair physics: Dynamic Bone (Assets/DynamicBone) — UniVRM dependency removed.
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
    public partial class AvatarController : MonoBehaviour
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

            // FR-A7-01: Delegate Animator setup/conflict-detection to GestureController (Issue #52)
            _gesture.InitializeAnimator(_animator);
            _currentGesture = "idle_alt";

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
                    _a2eInferer?.FeedA2FChunk(typedParams as A2fChunkParams);
                    break;
                case "a2f_stream_close":
                    _lipSync.HandleA2FStreamClose();
                    // FR-A2E-01: on-device Sentis inference (no-op when _a2eInferer is absent/not ready)
                    _a2eInferer?.InferAndApply(_emotion, _a2gGesture);
                    break;
                case "a2g_chunk":
                    _a2gGesture?.HandleA2GChunk(typedParams as A2gChunkParams);
                    break;
                case "a2g_stream_close":
                    _a2gGesture?.HandleA2GStreamClose();
                    break;
                case "a2e_emotion":
                    HandleA2EEmotion(typedParams as A2EEmotionParams);
                    break;
                case "set_background_mode":
                    HandleSetBackgroundMode(typedParams as SetBackgroundModeParams);
                    break;
                default:
                    // Unknown command: ignore (protocol: backward compatible)
                    Debug.Log($"[AvatarCtrl] Ignoring unknown cmd: {msg.cmd}");
                    break;
            }
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

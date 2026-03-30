// AvatarController.Handlers.cs
// Per-command handler methods for AvatarController (partial class).
// Extracted to keep AvatarController.cs as a thin dispatcher (Issue #52).
//
// SRS refs: FR-A7-01, FR-WS-01, FR-ROOM-02, FR-BEHAVIOR-SEQ-01, FR-A2E-01

using System;
using System.Collections.Generic;
using UnityEngine;
using AITuber.Room;
using AITuber.Growth;
using AITuber.Behavior;

namespace AITuber.Avatar
{
    public partial class AvatarController
    {
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

        /// <summary>Reset seated base-pose so walk transitions stand up properly.</summary>
        public void ResetSeatedBasePose() => _gesture.ResetSeatedBasePose();

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

        // ── set_background_mode (FR-BCAST-BG-01) ────────────────────

        private void HandleSetBackgroundMode(SetBackgroundModeParams p)
        {
            if (p == null || string.IsNullOrEmpty(p.mode)) return;
            var ctrl = Room.TransparentBackgroundController.Instance;
            if (ctrl != null)
                ctrl.SetMode(p.mode);
            else
                Debug.LogWarning("[AvatarCtrl] set_background_mode received but TransparentBackgroundController not found.");
        }

    }
}

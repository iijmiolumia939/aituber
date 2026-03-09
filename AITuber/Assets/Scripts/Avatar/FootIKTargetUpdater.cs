// FootIKTargetUpdater.cs
// Phase 5 — avatar-motion-roadmap.md
// Drives AvatarGrounding.FootIKBlend to enable foot IK in idle and disable it
// during walking, snapping, or when the avatar is not grounded.
//
// Design rationale:
//   Built-in Humanoid IK (Animator.SetIKPosition) is used instead of
//   com.unity.animation.rigging because AvatarGrounding already implements the
//   raycasting + SetIKPosition path in UpdateFootIK(). This updater only controls
//   the blend weight, acting as the "idle gating" layer described in Phase 5.
//
// Setup:
//   Add this component to the same GameObject as AvatarGrounding (i.e. AvatarRoot).
//   Enable "Foot IK (段差補正)" in AvatarGrounding's Inspector (_enableFootIK = true).
//   AvatarGrounding._ikWeight  sets the max IK weight (recommended 0.5 for first-pass).
//
// Runtime:
//   - Idle  : FootIKBlend → 1  (foot placement active)
//   - Walk  : FootIKBlend → 0  (walk anim not disturbed, foot locking avoided)
//   - Snap  : FootIKBlend → 0  (floor-drop in progress)
//   - Air   : FootIKBlend → 0  (mid-air, no ground contact)
//
// SRS refs: FR-LIFE-01 (avatar expresses natural idle behaviour in space)

using UnityEngine;

namespace AITuber.Avatar
{
    [RequireComponent(typeof(AvatarGrounding))]
    public class FootIKTargetUpdater : MonoBehaviour
    {
        [Header("Blend Settings")]
        [Tooltip("Speed (units/sec) at which FootIKBlend fades in and out. " +
                 "Lower values give smoother transitions; higher values are more responsive.")]
        [SerializeField, Range(0.5f, 10f)] private float _blendSpeed = 3f;

        [Tooltip("Seconds to wait after landing (Grounded=true) before fading IK in. " +
                 "Prevents a single-frame flicker when the avatar first touches ground.")]
        [SerializeField, Range(0f, 1f)] private float _groundedDelay = 0.15f;

        // ── Runtime ───────────────────────────────────────────────

        private AvatarGrounding _grounding;
        private float _currentBlend;
        private float _groundedTimer;   // counts up while Grounded, resets when airborne

        // ── Lifecycle ─────────────────────────────────────────────

        private void Awake()
        {
            _grounding = GetComponent<AvatarGrounding>();
        }

        private void Update()
        {
            // Accumulate grounded time so we don't snap IK on immediately after landing.
            if (_grounding.Grounded)
                _groundedTimer += Time.deltaTime;
            else
                _groundedTimer = 0f;

            float target = ShouldEnableIK() ? 1f : 0f;
            _currentBlend = Mathf.MoveTowards(_currentBlend, target, _blendSpeed * Time.deltaTime);
            _grounding.FootIKBlend = _currentBlend;
        }

        // ── Helpers ───────────────────────────────────────────────

        private bool ShouldEnableIK()
        {
            // BeginSnap is running — avatar may be in mid-air or still settling.
            if (_grounding.IsSnapping) return false;

            // Not yet stably grounded (airborne, or just landed within the delay window).
            if (_groundedTimer < _groundedDelay) return false;

            // Foot IK must be off while locomotion is active to avoid fighting walk animation.
            // Issue #51 (revised): read Animator "speed" param via AvatarGrounding.IsLocomoting
            // instead of a manually managed flag. Single Source of Truth = Animator parameter.
            if (_grounding.IsLocomoting) return false;

            return true;
        }
    }
}

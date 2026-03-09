// GazeControllerTests.cs
// EditMode unit tests for GazeController.
// TC-GZ-01 ~ TC-GZ-16
//
// Coverage:
//   GZ-01  Default state after AddComponent: IsRandomLookForTest=false, HasCommentGazeOverride=false
//   GZ-02  SetTarget("camera") → CurrentLookAtTargetForTest == camera Transform
//   GZ-03  SetTarget("chat")   → CurrentLookAtTargetForTest == chat Transform
//   GZ-04  SetTarget("down")   → CurrentLookAtTargetForTest == down Transform
//   GZ-05  SetTarget("center") → CurrentLookAtTargetForTest == camera Transform (alias)
//   GZ-06  SetTarget("random") → IsRandomLookForTest == true
//   GZ-07  SetTarget(unknown) → CurrentLookAtTargetForTest == camera Transform (fallback)
//   GZ-08  SetCommentGazeOverride(true)  → HasCommentGazeOverrideForTest == true
//   GZ-09  SetCommentGazeOverride(false) → HasCommentGazeOverrideForTest == false
//   GZ-10  SetHeadGestureActive(true)  → IsHeadGestureActiveForTest == true
//   GZ-11  SetHeadGestureActive(false) → IsHeadGestureActiveForTest == false
//   GZ-12  Initialize(null) → no exception (null animator guard in ApplyLookAtIK)
//   GZ-13  OnAnimatorIKFromProxy with null animator → no exception
//   GZ-14  LookAtInfluence when target is non-null → returns _lookAtWeight (0.8f default)
//   GZ-15  LookAtInfluence when no targets injected → returns 0f (null target)
//   GZ-16  SetTarget twice (camera → chat) → target updated to chat
//
// SRS: FR-A7-01, FR-WS-01
// Issue: #52 Phase 3

using NUnit.Framework;
using UnityEngine;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for GazeController.
    /// IK calls (OnAnimatorIKFromProxy → ApplyLookAtIK) are tested only for null-safety;
    /// full IK behavior tests require PlayMode with a live Animator.
    /// TC-GZ-01 ~ TC-GZ-16 / FR-A7-01 / FR-WS-01
    /// </summary>
    public class GazeControllerTests
    {
        private GameObject     _go;
        private GazeController _gc;

        // Injected look target stubs
        private Transform _camera;
        private Transform _chat;
        private Transform _down;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("GZ_Test");
            _gc = _go.AddComponent<GazeController>();

            // Create stub look target GameObjects
            _camera = new GameObject("Camera").transform;
            _chat   = new GameObject("Chat").transform;
            _down   = new GameObject("Down").transform;

            _gc.SetLookTargetsForTest(_camera, _chat, _down);
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_go);
            UnityEngine.Object.DestroyImmediate(_camera.gameObject);
            UnityEngine.Object.DestroyImmediate(_chat.gameObject);
            UnityEngine.Object.DestroyImmediate(_down.gameObject);
        }

        // ── TC-GZ-01: Default state ───────────────────────────────────────────

        [Test]
        public void TC_GZ_01_DefaultState_NotRandomNoCommentOverride()
        {
            // Fresh component (targets injected in SetUp)
            Assert.IsFalse(_gc.IsRandomLookForTest,            "should not be random by default");
            Assert.IsFalse(_gc.HasCommentGazeOverrideForTest,  "comment override should be off by default");
            Assert.IsFalse(_gc.IsHeadGestureActiveForTest,     "head gesture should be inactive by default");
        }

        // ── TC-GZ-02 ~ GZ-07: SetTarget ──────────────────────────────────────

        [Test]
        public void TC_GZ_02_SetTarget_Camera()
        {
            _gc.SetTarget("camera");
            Assert.AreEqual(_camera, _gc.CurrentLookAtTargetForTest);
            Assert.IsFalse(_gc.IsRandomLookForTest);
        }

        [Test]
        public void TC_GZ_03_SetTarget_Chat()
        {
            _gc.SetTarget("chat");
            Assert.AreEqual(_chat, _gc.CurrentLookAtTargetForTest);
        }

        [Test]
        public void TC_GZ_04_SetTarget_Down()
        {
            _gc.SetTarget("down");
            Assert.AreEqual(_down, _gc.CurrentLookAtTargetForTest);
        }

        [Test]
        public void TC_GZ_05_SetTarget_Center_AliasesToCamera()
        {
            _gc.SetTarget("center");
            Assert.AreEqual(_camera, _gc.CurrentLookAtTargetForTest,
                "\"center\" should alias to camera transform");
        }

        [Test]
        public void TC_GZ_06_SetTarget_Random_EnablesRandomMode()
        {
            _gc.SetTarget("random");
            Assert.IsTrue(_gc.IsRandomLookForTest,
                "IsRandomLookForTest should be true after SetTarget(\"random\")");
        }

        [Test]
        public void TC_GZ_07_SetTarget_Unknown_FallsBackToCamera()
        {
            _gc.SetTarget("outer_space");
            Assert.AreEqual(_camera, _gc.CurrentLookAtTargetForTest,
                "unknown target should fall back to camera");
        }

        // ── TC-GZ-08 ~ GZ-09: SetCommentGazeOverride ─────────────────────────

        [Test]
        public void TC_GZ_08_SetCommentGazeOverride_True()
        {
            _gc.SetCommentGazeOverride(true);
            Assert.IsTrue(_gc.HasCommentGazeOverrideForTest);
        }

        [Test]
        public void TC_GZ_09_SetCommentGazeOverride_False()
        {
            _gc.SetCommentGazeOverride(true);
            _gc.SetCommentGazeOverride(false);
            Assert.IsFalse(_gc.HasCommentGazeOverrideForTest);
        }

        // ── TC-GZ-10 ~ GZ-11: SetHeadGestureActive ───────────────────────────

        [Test]
        public void TC_GZ_10_SetHeadGestureActive_True()
        {
            _gc.SetHeadGestureActive(true);
            Assert.IsTrue(_gc.IsHeadGestureActiveForTest);
        }

        [Test]
        public void TC_GZ_11_SetHeadGestureActive_False()
        {
            _gc.SetHeadGestureActive(true);
            _gc.SetHeadGestureActive(false);
            Assert.IsFalse(_gc.IsHeadGestureActiveForTest);
        }

        // ── TC-GZ-12 ~ GZ-13: Null animator safety ───────────────────────────

        [Test]
        public void TC_GZ_12_Initialize_Null_NoException()
        {
            Assert.DoesNotThrow(() => _gc.Initialize(null));
        }

        [Test]
        public void TC_GZ_13_OnAnimatorIKFromProxy_NullAnimator_NoException()
        {
            _gc.Initialize(null);
            _gc.SetTarget("camera");
            Assert.DoesNotThrow(() => _gc.OnAnimatorIKFromProxy(0));
        }

        // ── TC-GZ-14 ~ GZ-15: LookAtInfluence ───────────────────────────────

        [Test]
        public void TC_GZ_14_LookAtInfluence_NonNullTarget_ReturnsWeight()
        {
            _gc.SetTarget("camera"); // sets _currentLookAtTarget = _camera (non-null)
            Assert.Greater(_gc.LookAtInfluence, 0f,
                "LookAtInfluence should be > 0 when target is set");
        }

        [Test]
        public void TC_GZ_15_LookAtInfluence_NullTargets_ReturnsZero()
        {
            // Inject null targets so _currentLookAtTarget resolves to null
            _gc.SetLookTargetsForTest(null, null, null);
            _gc.SetTarget("camera"); // switch falls through to null
            Assert.AreEqual(0f, _gc.LookAtInfluence,
                "LookAtInfluence should be 0 when all targets are null");
        }

        // ── TC-GZ-16: SetTarget twice updates correctly ───────────────────────

        [Test]
        public void TC_GZ_16_SetTarget_Twice_UpdatesTarget()
        {
            _gc.SetTarget("camera");
            Assert.AreEqual(_camera, _gc.CurrentLookAtTargetForTest);

            _gc.SetTarget("chat");
            Assert.AreEqual(_chat, _gc.CurrentLookAtTargetForTest,
                "second SetTarget should override the first");
        }
    }
}

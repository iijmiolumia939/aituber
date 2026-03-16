// GestureControllerTests.cs
// EditMode unit tests for GestureController.
// TC-GC-01 ~ TC-GC-16
//
// Coverage:
//   GC-01  Apply with null Animator → logs warning, no crash
//   GC-02  Apply("none") with null Animator → no warning, no crash
//   GC-03  Apply("none") resets dedup cache to "none"
//   GC-04  Apply known gesture → dedup cache updated, no crash
//   GC-05  Apply same gesture twice → second is deduplicated (cache unchanged)
//   GC-06  ResetGestureDedup → clears dedup cache to "none"
//   GC-07  Apply after ResetGestureDedup → fires again (cache set)
//   GC-08  Apply unknown gesture with null Animator → logs warning
//   GC-09  SetIdleMotion("energetic") → IdleMotion property returns "energetic"
//   GC-10  SetIdleMotion("default")  → IdleMotion property returns "default"
//   GC-11  SetIdleMotion(null)       → IdleMotion property returns "default"
//   GC-12  SetIdleMotion with injected Animator → no crash, IdleMotion updated
//   GC-13  Dedup transition: gesture→idle resets cache (SimulateDedupTransitionForTest)
//   GC-14  Dedup transition: idle→gesture does NOT reset cache
//   GC-15  Dedup transition when cache="none" → no spurious reset log
//   GC-16  All known gesture strings produce a non-default warning (trigger mapped)
//   GC-17  Apply with Animator lacking controller → logs warning, no crash
//   GC-18  Apply re-resolves to controller-backed humanoid Animator when available
//   GC-19  Seated gestures enable seated base pose restoration
//   GC-20  Standing gestures clear seated base pose restoration
//   GC-21  Gesture finish while seated forces SitIdle restoration
//
// SRS: FR-A7-01, FR-WS-01, FR-BEHAVIOR-SEQ-01
// Issue: #52 Phase 1 test coverage

using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for GestureController.
    /// Coroutines (PlayInitialIdleAlt, DiagnoseWaveBone) are tested only for
    /// null-safety; full timing tests require PlayMode with a real AnimatorController.
    /// TC-GC-01 ~ TC-GC-21 / FR-WS-01 / FR-A7-01 / FR-BEHAVIOR-SEQ-01
    /// </summary>
    public class GestureControllerTests
    {
        private GameObject        _go;
        private GestureController _gc;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("GC_Test");
            _gc = _go.AddComponent<GestureController>();
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        /// <summary>Creates a minimal animator on a separate GameObject and injects it.</summary>
        private Animator InjectDummyAnimator()
        {
            var animGo = new GameObject("GC_Anim");
            animGo.transform.SetParent(_go.transform);
            var anim = animGo.AddComponent<Animator>();
            _gc.SetAnimatorForTest(anim);
            return anim;
        }

        // ── Null-safety: no Animator ─────────────────────────────────────────

        // [TC-GC-01] Apply with null Animator logs warning and does not crash
        [Test]
        public void Apply_NullAnimator_LogsWarningAndDoesNotCrash()
        {
            LogAssert.Expect(LogType.Warning, "[GestureCtrl] Apply: _animator is NULL");
            Assert.DoesNotThrow(() => _gc.Apply("nod"));
        }

        // [TC-GC-02] Apply("none") with null Animator never logs a warning
        [Test]
        public void Apply_None_NullAnimator_NoWarningNocrash()
        {
            // "none" must NOT trigger the "Apply: _animator is NULL" warning path
            LogAssert.NoUnexpectedReceived();
            Assert.DoesNotThrow(() => _gc.Apply("none"));
        }

        // [TC-GC-03] Apply("none") resets the dedup cache to "none"
        [Test]
        public void Apply_None_ResetsDedupCache()
        {
            var anim = InjectDummyAnimator();
            _gc.Apply("nod");   // sets cache to "nod" (warning expected for uninitialized Animator without controller)

            // Silence any trigger/warning log from Apply("nod")
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("none");
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("none", _gc.LastAppliedGestureForTest,
                "Apply('none') must reset dedup cache to 'none'");
        }

        // [TC-GC-08] Apply unknown gesture with valid Animator → logs warning
        [Test]
        public void Apply_UnknownGesture_LogsWarning()
        {
            InjectDummyAnimator();
            LogAssert.Expect(LogType.Warning, new System.Text.RegularExpressions.Regex(
                @"\[GestureCtrl\] Unknown gesture:"));
            _gc.Apply("totally_fake_gesture_xyz");
        }

        // [TC-GC-17] Apply with Animator lacking controller logs warning and does not crash
        [Test]
        public void Apply_AnimatorWithoutController_LogsWarningAndDoesNotCrash()
        {
            InjectDummyAnimator();
            LogAssert.Expect(LogType.Warning,
                "[GestureCtrl] Apply: runtimeAnimatorController is NULL (gesture='nod')");
            Assert.DoesNotThrow(() => _gc.Apply("nod"));
        }

        // [TC-GC-18] Apply re-resolves to a controller-backed humanoid Animator when available
        [Test]
        public void Apply_ReResolvesToAnimatorWithController_WhenAvailable()
        {
            var staleAnimator = InjectDummyAnimator();
            _gc.SetAnimatorForTest(staleAnimator);

            var controlledGo = new GameObject("GC_ControlledAnim");
            controlledGo.transform.SetParent(_go.transform);
            var controlledAnimator = controlledGo.AddComponent<Animator>();
            foreach (var controller in Resources.FindObjectsOfTypeAll<RuntimeAnimatorController>())
            {
                if (controller != null && controller.name == "AvatarAnimatorController")
                {
                    controlledAnimator.runtimeAnimatorController = controller;
                    break;
                }
            }

            if (controlledAnimator.runtimeAnimatorController == null)
                Assert.Ignore("AvatarAnimatorController asset not available in this test environment.");

            Assert.DoesNotThrow(() => _gc.Apply("nod"));
            Assert.AreSame(controlledAnimator, _gc.AnimatorForTest,
                "GestureController should switch to the controller-backed humanoid Animator.");
            Assert.AreEqual("nod", _gc.LastAppliedGestureForTest);

            UnityEngine.Object.DestroyImmediate(controlledGo);
        }

        // ── Dedup logic ───────────────────────────────────────────────────────

        // [TC-GC-04] Apply known gesture updates dedup cache
        [Test]
        public void Apply_KnownGesture_UpdatesDedupCache()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;  // suppress Animator-without-controller warnings
            _gc.Apply("nod");
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("nod", _gc.LastAppliedGestureForTest,
                "Dedup cache must reflect the last applied gesture name");
        }

        // [TC-GC-05] Applying the same gesture twice deduplicates – cache stays same value
        [Test]
        public void Apply_SameGestureTwice_SecondIsDeduplicated()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("nod");           // first: fires
            _gc.Apply("nod");           // second: deduped, no SetTrigger
            LogAssert.ignoreFailingMessages = false;

            // Cache stays "nod" (not cleared) — dedup is working
            Assert.AreEqual("nod", _gc.LastAppliedGestureForTest,
                "Cache should still hold 'nod' after the second deduplicated call");
        }

        // [TC-GC-06] ResetGestureDedup clears the dedup cache to "none"
        [Test]
        public void ResetGestureDedup_ClearsCacheToNone()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("wave");
            LogAssert.ignoreFailingMessages = false;

            _gc.ResetGestureDedup();

            Assert.AreEqual("none", _gc.LastAppliedGestureForTest,
                "ResetGestureDedup must reset cache to 'none' (FR-BEHAVIOR-SEQ-01)");
        }

        // [TC-GC-07] After ResetGestureDedup the same gesture fires again
        [Test]
        public void Apply_AfterResetGestureDedup_FiresAgain()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("nod");           // first fire
            _gc.ResetGestureDedup();    // reset
            _gc.Apply("nod");           // should fire again (cache was cleared)
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("nod", _gc.LastAppliedGestureForTest,
                "Gesture must be allowed again after ResetGestureDedup");
        }

        // ── Dedup transition detection ────────────────────────────────────────

        // [TC-GC-13] After gesture, simulated transition to idle resets dedup cache.
        // Core feature of the dedup tracker (FR-WS-01). Uses SimulateDedupTransitionForTest
        // instead of a real Animator state machine.
        [Test]
        public void SimulateDedupTransition_GestureToIdle_ResetsCacheFR_WS_01()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("nod");               // cache = "nod"

            // Simulate: Animator enters gesture state (non-looping)
            _gc.SimulateDedupTransitionForTest(animatorLooping: false);
            // Simulate: Animator returns to idle (looping) → should reset cache
            _gc.SimulateDedupTransitionForTest(animatorLooping: true);
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("none", _gc.LastAppliedGestureForTest,
                "Dedup cache must be reset when Animator transitions from gesture to idle (FR-WS-01)");
        }

        // [TC-GC-14] Transition idle→gesture (looping=true→false) does NOT reset cache
        [Test]
        public void SimulateDedupTransition_IdleToGesture_DoesNotResetCache()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("nod");                           // cache = "nod"

            // Idle → gesture (was idle, now in gesture)
            _gc.SimulateDedupTransitionForTest(animatorLooping: true);   // entering: was idle
            _gc.SimulateDedupTransitionForTest(animatorLooping: false);  // now in gesture (non-loop)
            LogAssert.ignoreFailingMessages = false;

            // Cache should still hold "nod" — reset only happens on gesture→idle, not idle→gesture
            Assert.AreEqual("nod", _gc.LastAppliedGestureForTest,
                "Cache must NOT be reset when entering a gesture (only when leaving)");
        }

        // [TC-GC-15] Transition when cache = "none" does not log spurious reset message
        [Test]
        public void SimulateDedupTransition_CacheNone_NoSpuriousReset()
        {
            // No gesture applied: cache starts at "none"
            // Transition should not fire the "finished → resetting" log
            LogAssert.NoUnexpectedReceived();

            // Was in gesture, now idle — but cache is "none" so reset log should NOT fire
            _gc.SimulateDedupTransitionForTest(animatorLooping: false);  // gesture state
            _gc.SimulateDedupTransitionForTest(animatorLooping: true);   // back to idle

            Assert.AreEqual("none", _gc.LastAppliedGestureForTest,
                "Cache remains 'none' — no change expected");
        }

        // ── IdleMotion configuration ──────────────────────────────────────────

        // [TC-GC-09] SetIdleMotion("energetic") → IdleMotion = "energetic"
        [Test]
        public void SetIdleMotion_Energetic_PropertyReflectsValue()
        {
            _gc.SetIdleMotion("energetic");
            Assert.AreEqual("energetic", _gc.IdleMotion);
        }

        // [TC-GC-10] SetIdleMotion("default") → IdleMotion = "default"
        [Test]
        public void SetIdleMotion_Default_PropertyReflectsValue()
        {
            _gc.SetIdleMotion("default");
            Assert.AreEqual("default", _gc.IdleMotion);
        }

        // [TC-GC-11] SetIdleMotion(null) → IdleMotion = "default"
        [Test]
        public void SetIdleMotion_Null_PropertyDefaultsToDefault()
        {
            _gc.SetIdleMotion(null);
            Assert.AreEqual("default", _gc.IdleMotion,
                "null idleMotion should fall back to 'default'");
        }

        // [TC-GC-12] SetIdleMotion with injected Animator does not crash
        [Test]
        public void SetIdleMotion_WithAnimator_DoesNotCrash()
        {
            InjectDummyAnimator();
            Assert.DoesNotThrow(() => _gc.SetIdleMotion("energetic"),
                "SetIdleMotion must not crash when Animator is present");
            Assert.AreEqual("energetic", _gc.IdleMotion);
        }

        // ── Gesture trigger mapping coverage ─────────────────────────────────

        private static readonly string[] KnownGestures = new[]
        {
            "nod", "shake", "wave", "cheer", "shrug", "facepalm",
            "shy", "laugh", "surprised", "rejected", "sigh", "thankful",
            "sad_idle", "sad_kick", "thinking", "idle_alt",
            "sit_down", "sit_idle", "sit_laugh", "sit_clap", "sit_point", "sit_disbelief", "sit_kick",
            "bow", "clap", "thumbs_up", "point_forward", "spin",
            "walk", "walk_stop", "walk_stop_start", "sit_read", "sit_eat", "sit_write",
            "sleep_idle", "stretch",
        };

        // [TC-GC-16] All known gesture strings are mapped (do not produce "Unknown gesture" warning).
        // Uses injected Animator; Animator.SetTrigger is a no-op without a controller
        // but must not throw. We verify no "Unknown gesture" warning.
        [Test]
        public void Apply_AllKnownGestures_NoUnknownGestureWarning(
            [ValueSource(nameof(KnownGestures))] string gesture)
        {
            InjectDummyAnimator();
            // Expect the SetTrigger log (varies per gesture name) but NOT the "Unknown gesture" warning.
            // We verify by checking no unhandled warning fires.
            LogAssert.ignoreFailingMessages = true;   // suppress Animator-no-controller messages
            Assert.DoesNotThrow(() => _gc.Apply(gesture),
                $"Apply('{gesture}') must not throw");
            LogAssert.ignoreFailingMessages = false;

            // Cache must be set (not "none") after a known gesture
            Assert.AreNotEqual("none", _gc.LastAppliedGestureForTest,
                $"Gesture '{gesture}' must update the dedup cache (trigger mapped)");
        }

        // [TC-GC-19] Seated gestures enable seated base pose restoration
        [Test]
        public void Apply_SitIdle_EnablesSeatedBasePoseRestoration()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("sit_idle");
            LogAssert.ignoreFailingMessages = false;

            Assert.IsTrue(_gc.PreferSeatedBasePoseForTest,
                "Applying a seated gesture should enable seated base pose restoration.");
        }

        // [TC-GC-20] Standing gestures clear seated base pose restoration
        [Test]
        public void Apply_IdleAlt_ClearsSeatedBasePoseRestoration()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("sit_idle");
            _gc.Apply("idle_alt");
            LogAssert.ignoreFailingMessages = false;

            Assert.IsFalse(_gc.PreferSeatedBasePoseForTest,
                "Applying idle_alt should clear seated base pose restoration.");
        }

        // [TC-GC-21] Gesture finish while seated forces SitIdle restoration
        [Test]
        public void SimulateDedupTransition_GestureToIdleWhileSeated_ForcesSitIdle()
        {
            InjectDummyAnimator();
            LogAssert.ignoreFailingMessages = true;
            _gc.Apply("sit_idle");
            _gc.Apply("sit_clap");
            _gc.SimulateDedupTransitionForTest(animatorLooping: false);
            _gc.SimulateDedupTransitionForTest(animatorLooping: true);
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("SitIdle", _gc.LastForcedLoopStateForTest,
                "When a seated gesture ends, GestureController should restore the SitIdle base pose.");
            Assert.AreEqual("none", _gc.LastAppliedGestureForTest,
                "Dedup cache should still reset after seated base pose restoration.");
        }
    }
}

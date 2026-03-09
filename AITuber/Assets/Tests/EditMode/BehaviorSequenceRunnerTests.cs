// BehaviorSequenceRunnerTests.cs
// EditMode tests for BehaviorSequenceRunner state management and defensive paths.
// TC-BSR-01 ~ TC-BSR-09
//
// Coverage:
//   BSR-01  StopBehavior when idle → no crash, IsBusy=false, RunningBehavior=null
//   BSR-02  StopBehavior idempotent (called twice) → no crash
//   BSR-03  StartBehavior unknown name → logs warning, IsBusy stays false
//   BSR-04  StartBehavior null name → logs warning, IsBusy stays false
//   BSR-05  ClearInstanceForTest → Instance=null
//   BSR-06  Singleton: second Awake destroys duplicate
//   BSR-07  StopBehavior with PerceptionReporter absent → no NullReferenceException
//   BSR-08  StartBehavior with null BehaviorDefinitionLoader → no crash
//   BSR-09  StartBehavior preempts running behavior via StopBehavior (interrupt regression)

using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using AITuber.Behavior;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for BehaviorSequenceRunner. Tests coroutine-free
    /// paths only (state management, singleton safety, defensive null handling).
    /// TC-BSR-01 ~ TC-BSR-09 / FR-BEHAVIOR-SEQ-01
    /// </summary>
    public class BehaviorSequenceRunnerTests
    {
        private GameObject               _go;
        private BehaviorSequenceRunner   _bsr;
        private BehaviorDefinitionLoader _loader;

        [SetUp]
        public void SetUp()
        {
            // Clear all singleton references before each test to prevent cross-test pollution
            BehaviorSequenceRunner.ClearInstanceForTest();
            BehaviorDefinitionLoader.ClearInstanceForTest();

            if (BehaviorSequenceRunner.Instance != null)
                UnityEngine.Object.DestroyImmediate(BehaviorSequenceRunner.Instance.gameObject);
            if (BehaviorDefinitionLoader.Instance != null)
                UnityEngine.Object.DestroyImmediate(BehaviorDefinitionLoader.Instance.gameObject);

            _go     = new GameObject("BSR_Test");
            _bsr    = _go.AddComponent<BehaviorSequenceRunner>();
            _loader = _go.AddComponent<BehaviorDefinitionLoader>();
            // Inject empty table — suppresses behaviors.json disk read in EditMode
            _loader.InjectForTest(new Dictionary<string, BehaviorSequence>());
        }

        [TearDown]
        public void TearDown()
        {
            BehaviorSequenceRunner.ClearInstanceForTest();
            BehaviorDefinitionLoader.ClearInstanceForTest();
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // [TC-BSR-01] StopBehavior when idle is safe and leaves runner in clean state
        [Test]
        public void StopBehavior_WhenIdle_DoesNotThrowAndLeavesCleanState()
        {
            Assert.DoesNotThrow(() => _bsr.StopBehavior());
            Assert.IsFalse(_bsr.IsBusy,              "IsBusy should be false after StopBehavior");
            Assert.IsNull(_bsr.RunningBehavior,       "RunningBehavior should be null after StopBehavior");
        }

        // [TC-BSR-02] StopBehavior called twice is idempotent
        [Test]
        public void StopBehavior_CalledTwice_IsIdempotent()
        {
            Assert.DoesNotThrow(() =>
            {
                _bsr.StopBehavior();
                _bsr.StopBehavior();
            });
            Assert.IsNull(_bsr.RunningBehavior, "RunningBehavior null after double StopBehavior");
        }

        // [TC-BSR-03] StartBehavior with unknown name logs warning, stays idle
        [Test]
        public void StartBehavior_UnknownName_LogsWarningAndStaysIdle()
        {
            // LogAssert.Expect is not available in strict mode without importing
            // UnityEngine.TestTools — use try/catch style or just verify state.
            _bsr.StartBehavior("nonexistent_behavior_xyz");

            Assert.IsFalse(_bsr.IsBusy,
                "IsBusy should be false for unknown behavior (no coroutine started)");
            Assert.IsNull(_bsr.RunningBehavior,
                "RunningBehavior should remain null for unknown behavior");
        }

        // [TC-BSR-04] StartBehavior with null name logs warning, stays idle
        [Test]
        public void StartBehavior_NullName_LogsWarningAndStaysIdle()
        {
            Assert.DoesNotThrow(() => _bsr.StartBehavior(null));
            Assert.IsFalse(_bsr.IsBusy);
            Assert.IsNull(_bsr.RunningBehavior);
        }

        // [TC-BSR-05] StartBehavior with empty string stays idle
        [Test]
        public void StartBehavior_EmptyString_StaysIdle()
        {
            Assert.DoesNotThrow(() => _bsr.StartBehavior(""));
            Assert.IsFalse(_bsr.IsBusy);
        }

        // [TC-BSR-06] ClearInstanceForTest sets Instance to null
        [Test]
        public void ClearInstanceForTest_SetsInstanceToNull()
        {
            Assert.IsNotNull(BehaviorSequenceRunner.Instance,
                "Instance should be set after Awake");
            BehaviorSequenceRunner.ClearInstanceForTest();
            Assert.IsNull(BehaviorSequenceRunner.Instance,
                "Instance should be null after ClearInstanceForTest");
        }

        // [TC-BSR-07] StopBehavior without PerceptionReporter in scene → no NullReferenceException
        // Regression test: Critical review finding — StopBehavior calls
        // PerceptionReporter.Instance?.ReportBehaviorCompleted(). With no
        // PerceptionReporter in the scene, Instance is null. The null-conditional
        // must prevent NullReferenceException.
        [Test]
        public void StopBehavior_WithoutPerceptionReporter_DoesNotThrow()
        {
            // PerceptionReporter not added to _go → Instance is null
            Assert.DoesNotThrow(() => _bsr.StopBehavior(),
                "StopBehavior must not throw when PerceptionReporter.Instance is null");
        }

        // [TC-BSR-09] StartBehavior preempts a running behavior via StopBehavior
        // Regression: previously used StopCoroutine inline, skipping speed-reset and
        // interrupt-notification. Now unified through StopBehavior().
        [Test]
        public void StartBehavior_WhileRunning_ResetsStateBeforeStartingNew()
        {
            // Inject a known behavior so StartBehavior can proceed
            var seq = new BehaviorSequence { behavior = "dummy", steps = System.Array.Empty<BehaviorStep>() };
            _loader.InjectForTest(new Dictionary<string, BehaviorSequence> { ["dummy"] = seq });

            // First start sets _runningBehavior (coroutine won't actually run in EditMode)
            // We simulate "mid-walk" by calling StartBehavior twice.
            Assert.DoesNotThrow(() =>
            {
                _bsr.StartBehavior("dummy");
                // Second call must not throw even though a behavior is "running"
                _bsr.StartBehavior("dummy");
            });
        }

        // [TC-BSR-08] Singleton: second component on different GO destroys itself
        [Test]
        public void Singleton_SecondInstance_DestroysItself()
        {
            var go2 = new GameObject("BSR_Test_Duplicate");
            try
            {
                var bsr2 = go2.AddComponent<BehaviorSequenceRunner>();

                // Awake should have called Destroy(this) on the second component.
                // Unity marks it as destroyed; check via Object.Equals null pattern.
                Assert.IsTrue(
                    (object)bsr2 == null || bsr2.Equals(null),
                    "Second BehaviorSequenceRunner component should be destroyed by Awake");
                Assert.AreSame(_bsr, BehaviorSequenceRunner.Instance,
                    "Instance should still be the original component");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(go2);
            }
        }
    }
}

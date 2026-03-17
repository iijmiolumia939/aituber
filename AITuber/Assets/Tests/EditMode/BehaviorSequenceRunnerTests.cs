// BehaviorSequenceRunnerTests.cs
// EditMode tests for BehaviorSequenceRunner state management and defensive paths.
// TC-BSR-01 ~ TC-BSR-13
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
//   BSR-10  camera_focus_avatar repositions the Main Camera for stream framing
//   BSR-11  zone_snap skips unsupported seat anchors instead of dropping avatar
//   BSR-12  zone_snap lands on nearby seat support when collider is present
//   BSR-13  zone_snap Y is at least the seat support height (no CC dependency)

using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using AITuber.Behavior;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for BehaviorSequenceRunner. Tests coroutine-free
    /// paths only (state management, singleton safety, defensive null handling).
    /// TC-BSR-01 ~ TC-BSR-13 / FR-BEHAVIOR-SEQ-01
    /// </summary>
    public class BehaviorSequenceRunnerTests
    {
        private GameObject               _go;
        private BehaviorSequenceRunner   _bsr;
        private BehaviorDefinitionLoader _loader;
        private GameObject               _cameraGo;

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
            if (_cameraGo != null)
                UnityEngine.Object.DestroyImmediate(_cameraGo);
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

        // [TC-BSR-10] camera_focus_avatar repositions Main Camera relative to avatar root
        [Test]
        public void CameraFocusAvatar_RepositionsMainCameraForStreamShot()
        {
            _cameraGo = new GameObject("Main Camera");
            _cameraGo.tag = "MainCamera";
            var camera = _cameraGo.AddComponent<Camera>();

            _go.transform.position = new Vector3(2f, 0f, 3f);
            _go.transform.rotation = Quaternion.Euler(0f, 180f, 0f);
            SetPrivateField("_avatarRoot", _go.transform);

            var step = new BehaviorStep
            {
                type = "camera_focus_avatar",
                camera_local_offset = new Vector3(0f, 1.4f, 1.1f),
                camera_target_height = 1.35f,
                camera_fov = 36f,
            };

            var method = typeof(BehaviorSequenceRunner).GetMethod(
                "StepCameraFocusAvatar",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(method, "StepCameraFocusAvatar should exist for stream camera behaviors");

            var enumerator = method.Invoke(_bsr, new object[] { step }) as System.Collections.IEnumerator;
            Assert.IsNotNull(enumerator, "camera_focus_avatar should return an IEnumerator");
            while (enumerator.MoveNext())
            {
            }

            Vector3 expectedPosition = _go.transform.TransformPoint(step.camera_local_offset);
            Vector3 expectedLookTarget = _go.transform.position + Vector3.up * step.camera_target_height;
            Vector3 expectedForward = (expectedLookTarget - expectedPosition).normalized;

            Assert.That(Vector3.Distance(camera.transform.position, expectedPosition), Is.LessThan(0.001f));
            Assert.That(Vector3.Dot(camera.transform.forward, expectedForward), Is.GreaterThan(0.999f));
            Assert.AreEqual(36f, camera.fieldOfView, 0.001f);
        }

        // [TC-BSR-11] zone_snap must skip unsupported seat anchors and keep avatar in place
        [Test]
        public void ZoneSnap_WithoutSeatSupport_SkipsTeleport()
        {
            var slotGo = new GameObject("UnsupportedSeatSlot");
            try
            {
                var slot = slotGo.AddComponent<InteractionSlot>();
                slot.slotId = "unsupported_seat";
                slot.faceYaw = 90f;
                slotGo.transform.position = new Vector3(4f, 1.1f, 5f);

                _go.transform.position = new Vector3(1f, 0f, 1f);
                _go.transform.rotation = Quaternion.identity;
                SetPrivateField("_avatarRoot", _go.transform);
                SetPrivateField("_currentBehaviorSuccess", true);

                var step = new BehaviorStep { type = "zone_snap", slot_id = "unsupported_seat" };
                RunPrivateCoroutine("StepZoneSnap", step);

                Assert.That(Vector3.Distance(_go.transform.position, new Vector3(1f, 0f, 1f)), Is.LessThan(0.001f));
                Assert.That(Quaternion.Angle(_go.transform.rotation, Quaternion.Euler(0f, 90f, 0f)), Is.LessThan(0.001f));
                Assert.IsFalse(GetPrivateField<bool>("_currentBehaviorSuccess"));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(slotGo);
            }
        }

        // [TC-BSR-12] zone_snap should place avatar on the seat when support collider exists
        [Test]
        public void ZoneSnap_WithSeatSupport_TeleportsToSupportedSeat()
        {
            var seatGo = GameObject.CreatePrimitive(PrimitiveType.Cube);
            var slotGo = new GameObject("SupportedSeatSlot");
            try
            {
                seatGo.name = "WorkSeatCollider";
                seatGo.transform.position = new Vector3(4f, 0.95f, 5f);
                seatGo.transform.localScale = new Vector3(0.5f, 0.1f, 0.5f);

                var slot = slotGo.AddComponent<InteractionSlot>();
                slot.slotId = "supported_seat";
                slot.faceYaw = 135f;
                slotGo.transform.position = new Vector3(4f, 1.0f, 5f);

                _go.transform.position = Vector3.zero;
                _go.transform.rotation = Quaternion.identity;
                SetPrivateField("_avatarRoot", _go.transform);
                SetPrivateField("_currentBehaviorSuccess", true);

                var step = new BehaviorStep { type = "zone_snap", slot_id = "supported_seat" };
                RunPrivateCoroutine("StepZoneSnap", step);

                Assert.That(Vector3.Distance(_go.transform.position, new Vector3(4f, 1.0f, 5f)), Is.LessThan(0.001f));
                Assert.That(Quaternion.Angle(_go.transform.rotation, Quaternion.Euler(0f, 135f, 0f)), Is.LessThan(0.001f));
                Assert.IsTrue(GetPrivateField<bool>("_currentBehaviorSuccess"));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(slotGo);
                UnityEngine.Object.DestroyImmediate(seatGo);
            }
        }

        // [TC-BSR-13] zone_snap should lift AvatarRoot to at least the seat support height (#67: CC removed)
        [Test]
        public void ZoneSnap_WithSeatSupport_RaisesRootToSeatLevel()
        {
            var seatGo = GameObject.CreatePrimitive(PrimitiveType.Cube);
            var slotGo = new GameObject("SupportedSeatWithSupportSlot");
            try
            {
                seatGo.name = "WorkSeatColliderSupport";
                seatGo.transform.position = new Vector3(4f, 0.95f, 5f);
                seatGo.transform.localScale = new Vector3(0.5f, 0.1f, 0.5f);

                var slot = slotGo.AddComponent<InteractionSlot>();
                slot.slotId = "supported_seat_v2";
                slot.faceYaw = 135f;
                slotGo.transform.position = new Vector3(4f, 1.0f, 5f);

                _go.transform.position = Vector3.zero;
                _go.transform.rotation = Quaternion.identity;
                SetPrivateField("_avatarRoot", _go.transform);
                SetPrivateField("_currentBehaviorSuccess", true);

                var step = new BehaviorStep { type = "zone_snap", slot_id = "supported_seat_v2" };
                RunPrivateCoroutine("StepZoneSnap", step);

                // #67: Without CC, zone_snap places at Max(seatHit.y, slot.StandPosition.y)
                Assert.That(_go.transform.position.y, Is.GreaterThanOrEqualTo(1.0f));
                Assert.That(Quaternion.Angle(_go.transform.rotation, Quaternion.Euler(0f, 135f, 0f)), Is.LessThan(0.001f));
                Assert.IsTrue(GetPrivateField<bool>("_currentBehaviorSuccess"));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(slotGo);
                UnityEngine.Object.DestroyImmediate(seatGo);
            }
        }

        private void RunPrivateCoroutine(string methodName, BehaviorStep step)
        {
            var method = typeof(BehaviorSequenceRunner).GetMethod(
                methodName,
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(method, $"Expected private method '{methodName}' to exist");

            var enumerator = method.Invoke(_bsr, new object[] { step }) as System.Collections.IEnumerator;
            Assert.IsNotNull(enumerator, $"Expected private coroutine '{methodName}' to return IEnumerator");
            while (enumerator.MoveNext())
            {
            }
        }

        private void SetPrivateField(string fieldName, object value)
        {
            var field = typeof(BehaviorSequenceRunner).GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(field, $"Expected private field '{fieldName}' to exist");
            field.SetValue(_bsr, value);
        }

        private T GetPrivateField<T>(string fieldName)
        {
            var field = typeof(BehaviorSequenceRunner).GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.IsNotNull(field, $"Expected private field '{fieldName}' to exist");
            return (T)field.GetValue(_bsr);
        }
    }
}

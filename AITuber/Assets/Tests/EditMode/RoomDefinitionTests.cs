// RoomDefinitionTests.cs
// EditMode tests for RoomDefinition (ScriptableObject) and RoomManager guard clauses.
// SRS ref: FR-ROOM-01, FR-ROOM-02
// TC-ROOM-01 ~ TC-ROOM-18
//
// Coverage:
//   ROOM-01  RoomDefinition default roomId is null or empty string
//   ROOM-02  RoomDefinition default displayName is null or empty string
//   ROOM-03  RoomDefinition default useFadeTransition is true
//   ROOM-04  RoomDefinition default transitionDuration is 0.4f
//   ROOM-05  RoomDefinition default cameraFov is 40f
//   ROOM-06  RoomDefinition default cameraPosition is (0, 1.3, -1.5)
//   ROOM-07  RoomDefinition default cameraEuler is (5, 0, 0)
//   ROOM-08  RoomDefinition default avatarPosition is Vector3.zero
//   ROOM-09  RoomDefinition default avatarEuler is Vector3.zero
//   ROOM-10  Setting roomId persists the value
//   ROOM-11  Setting displayName persists the value
//   ROOM-12  Two RoomDefinition instances are independent
//   ROOM-13  RoomManager.CurrentRoomId returns empty string before Start()
//   ROOM-14  RoomManager.SwitchRoom("") does not throw
//   ROOM-15  RoomManager.SwitchRoom(null) does not throw
//   ROOM-16  RoomManager.SwitchRoom(unknown) does not throw when map is empty
//   ROOM-17  RoomManager singleton Instance is set after Awake()
//   ROOM-18  RoomDefinition default roomPrefab is null

using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using AITuber.Room;

namespace AITuber.Tests
{
    [TestFixture]
    public class RoomDefinitionTests
    {
        private readonly List<UnityEngine.Object> _toDestroy = new();

        private T CreateSO<T>() where T : ScriptableObject
        {
            var obj = ScriptableObject.CreateInstance<T>();
            _toDestroy.Add(obj);
            return obj;
        }

        private GameObject CreateGO(string name)
        {
            var go = new GameObject(name);
            _toDestroy.Add(go);
            return go;
        }

        [TearDown]
        public void TearDown()
        {
            RoomManager.ClearInstanceForTest();
            foreach (var obj in _toDestroy)
                if (obj != null)
                    UnityEngine.Object.DestroyImmediate(obj);
            _toDestroy.Clear();
        }

        // ── RoomDefinition default values ────────────────────────────

        // [TC-ROOM-01] roomId のデフォルトは null または空文字列
        [Test]
        public void RoomDefinition_Default_RoomId_IsNullOrEmpty()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.IsTrue(string.IsNullOrEmpty(def.roomId),
                "Default roomId should be null or empty");
        }

        // [TC-ROOM-02] displayName のデフォルトは null または空文字列
        [Test]
        public void RoomDefinition_Default_DisplayName_IsNullOrEmpty()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.IsTrue(string.IsNullOrEmpty(def.displayName),
                "Default displayName should be null or empty");
        }

        // [TC-ROOM-03] useFadeTransition のデフォルトは true
        [Test]
        public void RoomDefinition_Default_UseFadeTransition_IsTrue()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.IsTrue(def.useFadeTransition,
                "Default useFadeTransition should be true");
        }

        // [TC-ROOM-04] transitionDuration のデフォルトは 0.4f
        [Test]
        public void RoomDefinition_Default_TransitionDuration_Is0_4()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.AreEqual(0.4f, def.transitionDuration, 1e-6f,
                "Default transitionDuration should be 0.4f");
        }

        // [TC-ROOM-05] cameraFov のデフォルトは 40f
        [Test]
        public void RoomDefinition_Default_CameraFov_Is40()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.AreEqual(40f, def.cameraFov, 1e-6f,
                "Default cameraFov should be 40f");
        }

        // [TC-ROOM-06] cameraPosition のデフォルトは (0, 1.3, -1.5)
        [Test]
        public void RoomDefinition_Default_CameraPosition_IsExpected()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.AreEqual(  0f, def.cameraPosition.x, 1e-5f, "cameraPosition.x");
            Assert.AreEqual(1.3f, def.cameraPosition.y, 1e-5f, "cameraPosition.y");
            Assert.AreEqual(-1.5f, def.cameraPosition.z, 1e-5f, "cameraPosition.z");
        }

        // [TC-ROOM-07] cameraEuler のデフォルトは (5, 0, 0)
        [Test]
        public void RoomDefinition_Default_CameraEuler_IsExpected()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.AreEqual(5f, def.cameraEuler.x, 1e-5f, "cameraEuler.x");
            Assert.AreEqual(0f, def.cameraEuler.y, 1e-5f, "cameraEuler.y");
            Assert.AreEqual(0f, def.cameraEuler.z, 1e-5f, "cameraEuler.z");
        }

        // [TC-ROOM-08] avatarPosition のデフォルトは Vector3.zero
        [Test]
        public void RoomDefinition_Default_AvatarPosition_IsZero()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.AreEqual(Vector3.zero, def.avatarPosition,
                "Default avatarPosition should be Vector3.zero");
        }

        // [TC-ROOM-09] avatarEuler のデフォルトは Vector3.zero
        [Test]
        public void RoomDefinition_Default_AvatarEuler_IsZero()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.AreEqual(Vector3.zero, def.avatarEuler,
                "Default avatarEuler should be Vector3.zero");
        }

        // ── RoomDefinition serialization ─────────────────────────────

        // [TC-ROOM-10] roomId に値を設定すると保持される
        [Test]
        public void RoomDefinition_SetRoomId_PersistsValue()
        {
            var def = CreateSO<RoomDefinition>();
            def.roomId = "alchemist";
            Assert.AreEqual("alchemist", def.roomId);
        }

        // [TC-ROOM-11] displayName に値を設定すると保持される
        [Test]
        public void RoomDefinition_SetDisplayName_PersistsValue()
        {
            var def = CreateSO<RoomDefinition>();
            def.displayName = "錬金術師の部屋";
            Assert.AreEqual("錬金術師の部屋", def.displayName);
        }

        // [TC-ROOM-12] 2つのインスタンスは独立しており一方の変更が他方に影響しない
        [Test]
        public void RoomDefinition_TwoInstances_AreIndependent()
        {
            var defA = CreateSO<RoomDefinition>();
            var defB = CreateSO<RoomDefinition>();
            defA.roomId  = "room_a";
            defB.roomId  = "room_b";
            defA.cameraFov = 60f;

            Assert.AreEqual("room_a", defA.roomId,  "defA.roomId should be room_a");
            Assert.AreEqual("room_b", defB.roomId,  "defB.roomId should be room_b");
            Assert.AreEqual(60f, defA.cameraFov, 1e-6f, "defA.cameraFov should be 60");
            Assert.AreEqual(40f, defB.cameraFov, 1e-6f, "defB.cameraFov should remain 40");
        }

        // ── RoomManager guard clauses ────────────────────────────────

        // [TC-ROOM-13] Start() 前は CurrentRoomId が空文字列を返す
        [Test]
        public void RoomManager_CurrentRoomId_BeforeStart_IsEmpty()
        {
            RoomManager.ClearInstanceForTest();
            var go = CreateGO("RM_Test_13");
            var rm = go.AddComponent<RoomManager>();
            // Awake() runs, but Start() is NOT called in EditMode → _currentIndex stays -1
            Assert.AreEqual(string.Empty, rm.CurrentRoomId,
                "CurrentRoomId before Start should be empty string");
        }

        // [TC-ROOM-14] SwitchRoom("") は例外をスローしない
        [Test]
        public void RoomManager_SwitchRoom_EmptyId_DoesNotThrow()
        {
            RoomManager.ClearInstanceForTest();
            var go = CreateGO("RM_Test_14");
            var rm = go.AddComponent<RoomManager>();
            Assert.DoesNotThrow(() => rm.SwitchRoom(string.Empty));
        }

        // [TC-ROOM-15] SwitchRoom(null) は例外をスローしない
        [Test]
        public void RoomManager_SwitchRoom_NullId_DoesNotThrow()
        {
            RoomManager.ClearInstanceForTest();
            var go = CreateGO("RM_Test_15");
            var rm = go.AddComponent<RoomManager>();
            Assert.DoesNotThrow(() => rm.SwitchRoom((string)null));
        }

        // [TC-ROOM-16] 存在しない roomId で SwitchRoom を呼んでも例外をスローしない
        [Test]
        public void RoomManager_SwitchRoom_UnknownId_DoesNotThrow()
        {
            RoomManager.ClearInstanceForTest();
            var go = CreateGO("RM_Test_16");
            var rm = go.AddComponent<RoomManager>();
            Assert.DoesNotThrow(() => rm.SwitchRoom("nonexistent_room"));
        }

        // [TC-ROOM-17] Awake() 後は RoomManager.Instance が設定されている
        [Test]
        public void RoomManager_Singleton_InstanceSetAfterAwake()
        {
            RoomManager.ClearInstanceForTest();
            var go = CreateGO("RM_Test_17");
            var rm = go.AddComponent<RoomManager>();
            Assert.IsNotNull(RoomManager.Instance, "Instance should be set after Awake");
            Assert.AreSame(rm, RoomManager.Instance, "Instance should be the added component");
        }

        // [TC-ROOM-18] RoomDefinition の roomPrefab デフォルトは null
        [Test]
        public void RoomDefinition_Default_RoomPrefab_IsNull()
        {
            var def = CreateSO<RoomDefinition>();
            Assert.IsNull(def.roomPrefab, "Default roomPrefab should be null");
        }
    }
}

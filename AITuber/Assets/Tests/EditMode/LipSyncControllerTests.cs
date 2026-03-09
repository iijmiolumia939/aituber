// LipSyncControllerTests.cs
// EditMode unit tests for LipSyncController.
// TC-LS-01 ~ TC-LS-25
//
// Coverage:
//   LS-01  Default state: IsVisemePlayingForTest=false, TargetMouthOpenForTest=0, CurrentMouthOpenForTest=0, MouthSensitivityForTest=1
//   LS-02  SetMouthOpen(0.5f) → TargetMouthOpenForTest == 0.5f
//   LS-03  SetMouthOpen(-0.1f) → TargetMouthOpenForTest == 0f (clamped)
//   LS-04  SetMouthOpen(1.5f)  → TargetMouthOpenForTest == 1f (clamped)
//   LS-05  SetMouthSensitivity(2f) → MouthSensitivityForTest == 2f
//   LS-06  HandleViseme(null) → no exception, IsVisemePlayingForTest=false
//   LS-07  HandleViseme(empty events) → no exception, IsVisemePlayingForTest=false
//   LS-08  HandleViseme(valid params) → IsVisemePlayingForTest=true
//   LS-09  HandleViseme events are sorted by t_ms ascending
//   LS-10  HandleReset → TargetMouthOpenForTest=0, IsVisemePlayingForTest=false
//   LS-11  HandleReset → CurrentMouthOpenForTest=0
//   LS-12  IsA2FActive == false when no Audio2FaceLipSync component
//   LS-13  EstimatedA2FEmotion == "neutral" when no Audio2FaceLipSync component
//   LS-14  HandleA2FAudio(null) → no exception
//   LS-15  HandleA2FStreamClose() → no exception (no A2F wired)
//   LS-16  DoUpdate() with null faceMesh → no exception
//   LS-17  HandleA2FAudio float32 misaligned payload → no crash
//   LS-18  HandleReset with no A2F → no crash, viseme stops
//   LS-19  DoLateUpdate with null faceMesh → no crash
//   LS-20  Default LipSyncMode is A2FNeural (M21 / Issue #56 – changed from Hybrid)
//   LS-21  SetLipSyncMode(A2FNeural) → LipSyncModeForTest == A2FNeural (M21)
//   LS-22  In A2FNeural mode DoUpdate suppresses viseme (M21)
//   LS-23  In TtsViseme mode DoLateUpdate is a no-op without A2F wired (M21)
//   LS-24  In TtsViseme mode DoLateUpdate doesn't crash with null faceMesh (Re2 cleanup path)
//   LS-25  A2FNeural mode: HandleViseme accepted without exception, viseme suppressed after DoUpdate
//
// SRS: FR-LIPSYNC-01, FR-LIPSYNC-02
// Issue: #52 Phase 4 / #56 M21

using NUnit.Framework;
using UnityEngine;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for LipSyncController.
    /// A2F integration and blend-shape application require PlayMode with a live
    /// SkinnedMeshRenderer; these tests cover state logic and null-safety guards.
    /// TC-LS-01 ~ TC-LS-16 / FR-LIPSYNC-01 / FR-LIPSYNC-02
    /// </summary>
    public class LipSyncControllerTests
    {
        private GameObject        _go;
        private LipSyncController _ls;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("LS_Test");
            _ls = _go.AddComponent<LipSyncController>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_go);
        }

        // ── TC-LS-01: Default state ──────────────────────────────────────────

        [Test]
        public void TC_LS_01_DefaultState()
        {
            Assert.IsFalse(_ls.IsVisemePlayingForTest,               "viseme should not be playing");
            Assert.AreEqual(0f,  _ls.TargetMouthOpenForTest,  1e-4f, "targetMouthOpen should be 0");
            Assert.AreEqual(0f,  _ls.CurrentMouthOpenForTest, 1e-4f, "currentMouthOpen should be 0");
            Assert.AreEqual(1f,  _ls.MouthSensitivityForTest, 1e-4f, "sensitivity default is 1");
        }

        // ── TC-LS-02: SetMouthOpen normal value ──────────────────────────────

        [Test]
        public void TC_LS_02_SetMouthOpen_NormalValue()
        {
            _ls.SetMouthOpen(0.5f);
            Assert.AreEqual(0.5f, _ls.TargetMouthOpenForTest, 1e-4f);
        }

        // ── TC-LS-03: SetMouthOpen negative → clamped to 0 ──────────────────

        [Test]
        public void TC_LS_03_SetMouthOpen_NegativeClamped()
        {
            _ls.SetMouthOpen(-0.1f);
            Assert.AreEqual(0f, _ls.TargetMouthOpenForTest, 1e-4f);
        }

        // ── TC-LS-04: SetMouthOpen > 1 → clamped to 1 ───────────────────────

        [Test]
        public void TC_LS_04_SetMouthOpen_OverOneClamped()
        {
            _ls.SetMouthOpen(1.5f);
            Assert.AreEqual(1f, _ls.TargetMouthOpenForTest, 1e-4f);
        }

        // ── TC-LS-05: SetMouthSensitivity ────────────────────────────────────

        [Test]
        public void TC_LS_05_SetMouthSensitivity()
        {
            _ls.SetMouthSensitivity(2f);
            Assert.AreEqual(2f, _ls.MouthSensitivityForTest, 1e-4f);
        }

        // ── TC-LS-06: HandleViseme(null) → no crash ──────────────────────────

        [Test]
        public void TC_LS_06_HandleViseme_Null_NoException()
        {
            Assert.DoesNotThrow(() => _ls.HandleViseme(null));
            Assert.IsFalse(_ls.IsVisemePlayingForTest, "should remain not playing");
        }

        // ── TC-LS-07: HandleViseme(empty events) → no crash, not playing ─────

        [Test]
        public void TC_LS_07_HandleViseme_EmptyEvents_NoException()
        {
            var p = new AvatarVisemeParams { events = new VisemeEvent[0] };
            Assert.DoesNotThrow(() => _ls.HandleViseme(p));
            Assert.IsFalse(_ls.IsVisemePlayingForTest, "empty events should not start playback");
        }

        // ── TC-LS-08: HandleViseme(valid) → IsVisemePlayingForTest = true ────

        [Test]
        public void TC_LS_08_HandleViseme_ValidParams_SetsPlaying()
        {
            var p = new AvatarVisemeParams
            {
                events = new[]
                {
                    new VisemeEvent { t_ms = 0, v = "a" },
                    new VisemeEvent { t_ms = 200, v = "i" },
                },
                crossfade_ms = 60,
                strength = 1f,
            };
            _ls.HandleViseme(p);
            Assert.IsTrue(_ls.IsVisemePlayingForTest, "viseme should be playing after valid HandleViseme");
        }

        // ── TC-LS-09: Events are sorted by t_ms ascending ───────────────────

        [Test]
        public void TC_LS_09_HandleViseme_EventsSortedByTime()
        {
            // Supply events deliberately out of order; HandleViseme must sort them
            var p = new AvatarVisemeParams
            {
                events = new[]
                {
                    new VisemeEvent { t_ms = 300, v = "o" },
                    new VisemeEvent { t_ms = 100, v = "a" },
                    new VisemeEvent { t_ms = 200, v = "i" },
                },
                crossfade_ms = 60,
                strength = 1f,
            };
            _ls.HandleViseme(p);
            // After HandleViseme the events array should be sorted
            Assert.AreEqual(100, p.events[0].t_ms);
            Assert.AreEqual(200, p.events[1].t_ms);
            Assert.AreEqual(300, p.events[2].t_ms);
        }

        // ── TC-LS-10: HandleReset clears viseme + targetMouthOpen ────────────

        [Test]
        public void TC_LS_10_HandleReset_ClearsVisemeAndTarget()
        {
            // Prime state
            _ls.SetMouthOpen(0.8f);
            var p = new AvatarVisemeParams
            {
                events = new[] { new VisemeEvent { t_ms = 0, v = "a" } },
                crossfade_ms = 60,
                strength = 1f,
            };
            _ls.HandleViseme(p);
            Assert.IsTrue(_ls.IsVisemePlayingForTest);

            _ls.HandleReset();

            Assert.IsFalse(_ls.IsVisemePlayingForTest,             "viseme should stop on reset");
            Assert.AreEqual(0f, _ls.TargetMouthOpenForTest, 1e-4f, "targetMouthOpen should be 0 on reset");
        }

        // ── TC-LS-11: HandleReset clears currentMouthOpen ───────────────────

        [Test]
        public void TC_LS_11_HandleReset_ClearsCurrentMouthOpen()
        {
            _ls.HandleReset();
            Assert.AreEqual(0f, _ls.CurrentMouthOpenForTest, 1e-4f);
        }

        // ── TC-LS-12: IsA2FActive == false without Audio2FaceLipSync ────────

        [Test]
        public void TC_LS_12_IsA2FActive_FalseWhenNoComponent()
        {
            // _a2fLipSync is null (not set via SetA2FLipSyncForTest)
            Assert.IsFalse(_ls.IsA2FActive);
        }

        // ── TC-LS-13: EstimatedA2FEmotion == "neutral" without A2F ──────────

        [Test]
        public void TC_LS_13_EstimatedA2FEmotion_NeutralWhenNoComponent()
        {
            Assert.AreEqual("neutral", _ls.EstimatedA2FEmotion);
        }

        // ── TC-LS-14: HandleA2FAudio(null) → no crash ───────────────────────

        [Test]
        public void TC_LS_14_HandleA2FAudio_Null_NoException()
        {
            Assert.DoesNotThrow(() => _ls.HandleA2FAudio(null));
        }

        // ── TC-LS-15: HandleA2FStreamClose() → no crash ─────────────────────

        [Test]
        public void TC_LS_15_HandleA2FStreamClose_NoException()
        {
            // No A2F wired — should complete silently
            Assert.DoesNotThrow(() => _ls.HandleA2FStreamClose());
        }

        // ── TC-LS-16: DoUpdate() with null faceMesh → no crash ───────────────

        [Test]
        public void TC_LS_16_DoUpdate_NullFaceMesh_NoException()
        {
            // _faceMesh is null by default (not injected via SetFaceMeshForTest)
            Assert.DoesNotThrow(() => _ls.DoUpdate());
        }

        // ── TC-LS-17: HandleA2FAudio float32 misaligned payload → no crash ───

        [Test]
        public void TC_LS_17_HandleA2FAudio_MisalignedFloat32_NoException()
        {
            // 5 bytes: Length/4=1 sample, BlockCopy should copy only samples*4=4 bytes
            // Without the fix this throws ArgumentException on Buffer.BlockCopy
            byte[] raw = new byte[] { 0, 0, 0, 0, 0xFF }; // 5 bytes — not a multiple of 4
            string b64 = System.Convert.ToBase64String(raw);
            var p = new A2FAudioParams { pcm_b64 = b64, format = "float32", sample_rate = 16000 };
            // HandleA2FAudio returns early if _a2fLipSync is not ready — the decode path still runs
            Assert.DoesNotThrow(() => _ls.HandleA2FAudio(p));
        }

        // ── TC-LS-18: HandleReset stops IsVisemePlayingForTest ───────────────
        //   (verifies A2F?.CloseStream() guard doesn't crash when A2F is null)

        [Test]
        public void TC_LS_18_HandleReset_WithNoA2F_NoException()
        {
            var p = new AvatarVisemeParams
            {
                events = new[] { new VisemeEvent { t_ms = 0, v = "a" } },
                crossfade_ms = 60,
                strength = 1f,
            };
            _ls.HandleViseme(p);
            Assert.DoesNotThrow(() => _ls.HandleReset());
            Assert.IsFalse(_ls.IsVisemePlayingForTest);
        }

        // ── TC-LS-19: DoLateUpdate with null faceMesh → no crash ─────────────

        [Test]
        public void TC_LS_19_DoLateUpdate_NullFaceMesh_NoException()
        {
            Assert.DoesNotThrow(() => _ls.DoLateUpdate());
        }

        // ── TC-LS-20: Default LipSyncMode is A2FNeural (M21 / Issue #56) ─────────

        [Test]
        public void TC_LS_20_DefaultLipSyncMode_IsA2FNeural()
        {
            Assert.AreEqual(LipSyncMode.A2FNeural, _ls.LipSyncModeForTest,
                "Default mode must be A2FNeural (Issue #56: A2F neural takes precedence for best quality)");
        }

        // ── TC-LS-21: SetLipSyncMode(A2FNeural) → mode changes (M21) ─────────

        [Test]
        public void TC_LS_21_SetLipSyncMode_A2FNeural_Changes()
        {
            _ls.SetLipSyncMode(LipSyncMode.A2FNeural);
            Assert.AreEqual(LipSyncMode.A2FNeural, _ls.LipSyncModeForTest);
        }

        // ── TC-LS-22: A2FNeural mode — DoUpdate suppresses viseme (M21) ───────
        // When mode=A2FNeural, viseme should stop playing after DoUpdate even
        // without an actual A2F component driving IsSpeaking.

        [Test]
        public void TC_LS_22_A2FNeuralMode_DoUpdate_SuppressesViseme()
        {
            _ls.SetLipSyncMode(LipSyncMode.A2FNeural);

            // Prime viseme state
            var p = new AvatarVisemeParams
            {
                events = new[] { new VisemeEvent { t_ms = 0, v = "a" } },
                crossfade_ms = 60,
                strength = 1f,
            };
            _ls.HandleViseme(p);
            Assert.IsTrue(_ls.IsVisemePlayingForTest, "precondition: viseme playing");

            // A2FNeural mode must suppress viseme on next DoUpdate
            _ls.DoUpdate();

            Assert.IsFalse(_ls.IsVisemePlayingForTest,
                "In A2FNeural mode, DoUpdate must set _visemePlaying=false");
        }

        // ── TC-LS-23: TtsViseme mode — DoLateUpdate is a no-op without A2F (M21) ─

        [Test]
        public void TC_LS_23_TtsVisemeMode_DoLateUpdate_NoA2F_NoException()
        {
            // No A2F wired; TtsViseme mode should return early without crashing.
            _ls.SetLipSyncMode(LipSyncMode.TtsViseme);
            Assert.DoesNotThrow(() => _ls.DoLateUpdate(),
                "TtsViseme mode DoLateUpdate (no A2F) must not throw");
        }

        // ── TC-LS-24: TtsViseme mode + null faceMesh — Re2 cleanup path safe ───
        // Verifies that the Re2 FadeToZero cleanup guard in DoLateUpdate does not
        // crash when _faceMesh is null (guard condition: a2fLipSync == null path).

        [Test]
        public void TC_LS_24_TtsVisemeMode_DoLateUpdate_NullFaceMesh_NoException()
        {
            // _faceMesh is null (not injected); _a2fLipSync is null (not injected).
            // DoLateUpdate must return from the null faceMesh guard before any writes.
            _ls.SetLipSyncMode(LipSyncMode.TtsViseme);
            Assert.DoesNotThrow(() => _ls.DoLateUpdate(),
                "TtsViseme mode DoLateUpdate with null faceMesh must not throw");
        }

        // ── TC-LS-25: A2FNeural default — HandleViseme accepted, suppressed (Issue #56) ─
        // Verifies that in the default A2FNeural mode:
        //   1. HandleViseme does not throw (events are stored)
        //   2. DoUpdate immediately clears _visemePlaying (A2F has full control)

        [Test]
        public void TC_LS_25_A2FNeuralDefault_HandleViseme_ThenDoUpdate_SuppressedImmediately()
        {
            // Default mode is A2FNeural — confirm
            Assert.AreEqual(LipSyncMode.A2FNeural, _ls.LipSyncModeForTest);

            var p = new AvatarVisemeParams
            {
                events       = new[] { new VisemeEvent { t_ms = 0, v = "a" }, new VisemeEvent { t_ms = 200, v = "i" } },
                crossfade_ms = 60,
                strength     = 1f,
            };
            // HandleViseme must not throw even in A2FNeural mode
            Assert.DoesNotThrow(() => _ls.HandleViseme(p), "HandleViseme must not throw in A2FNeural mode");

            // DoUpdate must suppress: _visemePlaying → false
            _ls.DoUpdate();

            Assert.IsFalse(_ls.IsVisemePlayingForTest,
                "A2FNeural mode: DoUpdate must suppress viseme so A2F neural has exclusive mouth control");
        }
    }
}

// EmotionControllerTests.cs
// EditMode unit tests for EmotionController.
// TC-EC-01 ~ TC-EC-16
//
// Coverage:
//   EC-01  Apply("neutral")   → LastAppliedEmotionForTest recorded correctly
//   EC-02  Apply("happy")     → LastAppliedEmotionForTest recorded correctly
//   EC-03  Apply("angry")     → LastAppliedEmotionForTest recorded correctly
//   EC-04  Apply("sad")       → LastAppliedEmotionForTest recorded correctly
//   EC-05  Apply("surprised") → LastAppliedEmotionForTest recorded correctly
//   EC-06  Apply("panic")     → LastAppliedEmotionForTest recorded correctly
//   EC-07  Apply("thinking")  → LastAppliedEmotionForTest recorded correctly
//   EC-08  Apply(unknown)     → no exception, emotion string recorded
//   EC-09  Apply with null faceMesh → no crash (null guard active)
//   EC-10  SetBlinkEnabled(false) and SetBlinkEnabled(true) → no crash
//   EC-11  Apply("happy") → blink intervals tightened (min≤1.5f, max≤3.0f)
//   EC-12  Apply("sad") → blink intervals slowed (min=4.0f, max=8.0f, duration=0.20f)
//   EC-13  Apply("surprised") → blink paused ~5 s (nextBlinkTime ≥ Time.time+4f)
//   EC-14  Apply("panic") → same blink-pause behaviour as "surprised"
//   EC-15  Apply("neutral") after Apply("sad") → blink params restored to defaults
//   EC-16  All 7 known-emotion strings (parametrized) → Apply records each correctly
//
// SRS: FR-EMOTION-01, FR-A7-01
// Issue: #52 Phase 2

using NUnit.Framework;
using UnityEngine;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for EmotionController.
    /// OnEnable is triggered by AddComponent, so _defaultBlink* values are
    /// cached from the SerializedField defaults (2.5 / 6.0 / 0.12) before each test.
    /// TC-EC-01 ~ TC-EC-16 / FR-EMOTION-01 / FR-A7-01
    /// </summary>
    public class EmotionControllerTests
    {
        private const float DefaultBlinkIntervalMin = 2.5f;
        private const float DefaultBlinkIntervalMax = 6.0f;
        private const float DefaultBlinkDuration    = 0.12f;

        private GameObject         _go;
        private EmotionController  _ec;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("EC_Test");
            _ec = _go.AddComponent<EmotionController>();
            // OnEnable fires during AddComponent → defaults are cached.
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // ── TC-EC-01 ~ TC-EC-07: Apply records emotion string ────────────────

        [Test]
        public void TC_EC_01_Apply_Neutral_RecordsEmotion()
        {
            _ec.Apply("neutral");
            Assert.AreEqual("neutral", _ec.LastAppliedEmotionForTest);
        }

        [Test]
        public void TC_EC_02_Apply_Happy_RecordsEmotion()
        {
            _ec.Apply("happy");
            Assert.AreEqual("happy", _ec.LastAppliedEmotionForTest);
        }

        [Test]
        public void TC_EC_03_Apply_Angry_RecordsEmotion()
        {
            _ec.Apply("angry");
            Assert.AreEqual("angry", _ec.LastAppliedEmotionForTest);
        }

        [Test]
        public void TC_EC_04_Apply_Sad_RecordsEmotion()
        {
            _ec.Apply("sad");
            Assert.AreEqual("sad", _ec.LastAppliedEmotionForTest);
        }

        [Test]
        public void TC_EC_05_Apply_Surprised_RecordsEmotion()
        {
            _ec.Apply("surprised");
            Assert.AreEqual("surprised", _ec.LastAppliedEmotionForTest);
        }

        [Test]
        public void TC_EC_06_Apply_Panic_RecordsEmotion()
        {
            _ec.Apply("panic");
            Assert.AreEqual("panic", _ec.LastAppliedEmotionForTest);
        }

        [Test]
        public void TC_EC_07_Apply_Thinking_RecordsEmotion()
        {
            _ec.Apply("thinking");
            Assert.AreEqual("thinking", _ec.LastAppliedEmotionForTest);
        }

        // ── TC-EC-08: Unknown emotion ─────────────────────────────────────────

        [Test]
        public void TC_EC_08_Apply_Unknown_NoExceptionRecordsString()
        {
            Assert.DoesNotThrow(() => _ec.Apply("pirate_mode"));
            Assert.AreEqual("pirate_mode", _ec.LastAppliedEmotionForTest);
        }

        // ── TC-EC-09: Null faceMesh guard ─────────────────────────────────────

        [Test]
        public void TC_EC_09_Apply_NullFaceMesh_NoException()
        {
            // Default: no faceMesh injected → _faceMesh is null.
            // SetIndicesForTest activates a blend index so the code paths are exercised.
            _ec.SetIndicesForTest(0, 1, 2, 3, 4, 5);
            Assert.DoesNotThrow(() => _ec.Apply("happy"));
            Assert.DoesNotThrow(() => _ec.Apply("neutral")); // also resets previous index
        }

        // ── TC-EC-10: SetBlinkEnabled ────────────────────────────────────────

        [Test]
        public void TC_EC_10_SetBlinkEnabled_NoException()
        {
            Assert.DoesNotThrow(() => _ec.SetBlinkEnabled(false));
            Assert.DoesNotThrow(() => _ec.SetBlinkEnabled(true));
        }

        // ── TC-EC-11: Apply("happy") tightens blink interval ─────────────────

        [Test]
        public void TC_EC_11_Apply_Happy_TightensBlink()
        {
            _ec.Apply("happy");

            Assert.LessOrEqual(_ec.BlinkIntervalMinForTest, 1.5f,
                "happy blink interval min should be ≤ 1.5 s");
            Assert.LessOrEqual(_ec.BlinkIntervalMaxForTest, 3.0f,
                "happy blink interval max should be ≤ 3.0 s");
            Assert.AreEqual(DefaultBlinkDuration, _ec.BlinkDurationForTest, 1e-5f,
                "happy should not change blink duration");
        }

        // ── TC-EC-12: Apply("sad") slows blink ───────────────────────────────

        [Test]
        public void TC_EC_12_Apply_Sad_SlowsBlink()
        {
            _ec.Apply("sad");

            Assert.AreEqual(4.0f, _ec.BlinkIntervalMinForTest, 1e-5f);
            Assert.AreEqual(8.0f, _ec.BlinkIntervalMaxForTest, 1e-5f);
            Assert.AreEqual(0.20f, _ec.BlinkDurationForTest,   1e-5f);
        }

        // ── TC-EC-13: Apply("surprised") pauses blink ~5 s ───────────────────

        [Test]
        public void TC_EC_13_Apply_Surprised_PausesBlink()
        {
            _ec.Apply("surprised");

            Assert.IsFalse(_ec.IsBlinkingForTest,
                "surprised should immediately clear _isBlinking");
            Assert.GreaterOrEqual(_ec.NextBlinkTimeForTest, Time.time + 4f,
                "next blink should be deferred by ~5 s");
        }

        // ── TC-EC-14: Apply("panic") behaves identically to "surprised" ───────

        [Test]
        public void TC_EC_14_Apply_Panic_PausesBlinkLikeSurprised()
        {
            _ec.Apply("panic");

            Assert.IsFalse(_ec.IsBlinkingForTest);
            Assert.GreaterOrEqual(_ec.NextBlinkTimeForTest, Time.time + 4f);
        }

        // ── TC-EC-15: Defaults restored after "sad" ───────────────────────────

        [Test]
        public void TC_EC_15_Apply_Neutral_AfterSad_RestoresDefaults()
        {
            _ec.Apply("sad");
            _ec.Apply("neutral");

            Assert.AreEqual(DefaultBlinkIntervalMin, _ec.BlinkIntervalMinForTest, 1e-5f,
                "interval min should be restored to Inspector default");
            Assert.AreEqual(DefaultBlinkIntervalMax, _ec.BlinkIntervalMaxForTest, 1e-5f,
                "interval max should be restored to Inspector default");
            Assert.AreEqual(DefaultBlinkDuration,   _ec.BlinkDurationForTest,    1e-5f,
                "duration should be restored to Inspector default");
        }

        // ── TC-EC-16: Parametrized — all known emotions apply cleanly ─────────

        [Test]
        [TestCase("neutral")]
        [TestCase("happy")]
        [TestCase("angry")]
        [TestCase("sad")]
        [TestCase("surprised")]
        [TestCase("panic")]
        [TestCase("thinking")]
        public void TC_EC_16_AllKnownEmotions_ApplyWithoutException(string emotion)
        {
            Assert.DoesNotThrow(() => _ec.Apply(emotion));
            Assert.AreEqual(emotion, _ec.LastAppliedEmotionForTest);
        }
    }
}

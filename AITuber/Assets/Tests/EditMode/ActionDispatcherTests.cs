// ActionDispatcherTests.cs
// EditMode tests for ActionDispatcher.Dispatch / CategorizeGap.
// TC-ADSP-01 ~ TC-ADSP-08

using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using AITuber.Avatar;
using AITuber.Growth;

namespace AITuber.Tests
{
    public class ActionDispatcherTests
    {
        private GameObject _go;
        private ActionDispatcher _dispatcher;
        private GapLogger _logger;
        private BehaviorPolicyLoader _policyLoader;
        private string _tempLogPath;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("AD_Test");

            // Order matters: Awake runs on AddComponent
            _logger       = _go.AddComponent<GapLogger>();
            _policyLoader = _go.AddComponent<BehaviorPolicyLoader>();
            _dispatcher   = _go.AddComponent<ActionDispatcher>();

            _tempLogPath = Path.Combine(Path.GetTempPath(), $"adtest_{Guid.NewGuid():N}.jsonl");
            _logger.SetLogPathForTest(_tempLogPath);
            _logger.SetEnabled(true);
            _logger.ResetCountForTest();

            // Inject a minimal policy with one known intent
            _policyLoader.InjectForTest(new Dictionary<string, BehaviorEntry>
            {
                ["nod_agreement"] = new BehaviorEntry
                {
                    intent  = "nod_agreement",
                    cmd     = "avatar_update",
                    gesture = "nod",
                },
            });
        }

        [TearDown]
        public void TearDown()
        {
            if (File.Exists(_tempLogPath)) File.Delete(_tempLogPath);
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // [TC-ADSP-01] ポリシーに登録されたintentはExecutedを返す
        [Test]
        public void Dispatch_PolicyHit_ReturnsExecuted()
        {
            var p = new AvatarIntentParams { intent = "nod_agreement" };
            var result = _dispatcher.Dispatch(p);
            Assert.AreEqual(ActionDispatcher.DispatchResult.Executed, result);
        }

        // [TC-ADSP-02] ポリシーHitの場合GapLoggerに記録しない
        [Test]
        public void Dispatch_PolicyHit_NoGapLogged()
        {
            var p = new AvatarIntentParams { intent = "nod_agreement" };
            _dispatcher.Dispatch(p);
            Assert.AreEqual(0, _logger.GapCountThisSession, "Policy hit must not produce a Gap");
        }

        // [TC-ADSP-03] 未登録intentかつfallback指定あり → FallbackExecuted
        [Test]
        public void Dispatch_UnknownIntent_WithFallback_ReturnsFallbackExecuted()
        {
            var p = new AvatarIntentParams { intent = "point_at_screen", fallback = "nod" };
            var result = _dispatcher.Dispatch(p);
            Assert.AreEqual(ActionDispatcher.DispatchResult.FallbackExecuted, result);
        }

        // [TC-ADSP-04] 未登録intentはGapLoggerに1件記録される
        [Test]
        public void Dispatch_UnknownIntent_GapLogged()
        {
            var p = new AvatarIntentParams { intent = "point_at_screen", fallback = "nod" };
            _dispatcher.Dispatch(p);

            Assert.AreEqual(1, _logger.GapCountThisSession);
            string content = File.ReadAllText(_tempLogPath);
            StringAssert.Contains("\"point_at_screen\"", content);
            StringAssert.Contains("\"nod\"", content);
        }

        // [TC-ADSP-05] fallbackが空またはnoneの場合はSkippedを返す
        [Test]
        public void Dispatch_UnknownIntent_EmptyFallback_ReturnsSkipped()
        {
            var pEmpty = new AvatarIntentParams { intent = "unknown_xyz", fallback = "" };
            Assert.AreEqual(ActionDispatcher.DispatchResult.Skipped, _dispatcher.Dispatch(pEmpty));

            var pNone = new AvatarIntentParams { intent = "unknown_xyz2", fallback = "none" };
            Assert.AreEqual(ActionDispatcher.DispatchResult.Skipped, _dispatcher.Dispatch(pNone));
        }

        // [TC-ADSP-06] nullパラメーターはErrorを返す（例外なし）
        [Test]
        public void Dispatch_NullParams_ReturnsError_NoException()
        {
            ActionDispatcher.DispatchResult result = default;
            Assert.DoesNotThrow(() => result = _dispatcher.Dispatch(null));
            Assert.AreEqual(ActionDispatcher.DispatchResult.Error, result);
        }

        // [TC-ADSP-07] Gapカテゴリが命名規則プレフィックスで正しく推定される
        [Test]
        public void CategorizeGap_ByNamingConvention()
        {
            Assert.AreEqual("missing_motion",      ActionDispatcher.CategorizeGap("gesture_point_forward"));
            Assert.AreEqual("missing_motion",      ActionDispatcher.CategorizeGap("emote_laugh_big"));
            Assert.AreEqual("missing_behavior",    ActionDispatcher.CategorizeGap("event_superchat"));
            Assert.AreEqual("missing_integration", ActionDispatcher.CategorizeGap("integrate_bgm"));
            Assert.AreEqual("environment_limit",   ActionDispatcher.CategorizeGap("env_prop_book"));
            Assert.AreEqual("capability_limit",    ActionDispatcher.CategorizeGap("do_something_new"));
            Assert.AreEqual("unknown",             ActionDispatcher.CategorizeGap(""));
            Assert.AreEqual("unknown",             ActionDispatcher.CategorizeGap(null));
        }

        // [TC-ADSP-08] 同一セッションで複数Gapが全件記録される
        [Test]
        public void Dispatch_MultipleUnknownIntents_AllGapsLogged()
        {
            _dispatcher.Dispatch(new AvatarIntentParams { intent = "gesture_a", fallback = "nod" });
            _dispatcher.Dispatch(new AvatarIntentParams { intent = "gesture_b", fallback = "nod" });
            _dispatcher.Dispatch(new AvatarIntentParams { intent = "gesture_c", fallback = "" });

            Assert.AreEqual(3, _logger.GapCountThisSession);
        }
    }
}

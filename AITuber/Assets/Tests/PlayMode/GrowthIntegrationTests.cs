// GrowthIntegrationTests.cs
// PlayMode integration tests for the complete dispatch pipeline.
// TC-INTG-01 ~ TC-INTG-06
//
// Coverage:
//   INTG-01  avatar_intent WS message flows through ActionDispatcher → Executed
//   INTG-02  Missed intent logs a GapEntry (GapCountThisSession == 1)
//   INTG-03  Logged GapEntry contains correct intent name
//   INTG-04  Logged GapEntry.gap_category = "missing_motion" for gesture_* intent
//   INTG-05  Logged GapEntry.trigger = "avatar_intent_ws"
//   INTG-06  avatar_event message processes without recording a Gap

using System.IO;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using AITuber.Avatar;
using AITuber.Growth;

namespace AITuber.Tests
{
    public class GrowthIntegrationTests
    {
        private GameObject            _go;
        private GapLogger             _logger;
        private BehaviorPolicyLoader  _policy;
        private ActionDispatcher      _dispatcher;
        private AvatarController      _controller;
        private string                _tempPath;

        [SetUp]
        public void SetUp()
        {
            _go         = new GameObject("INTG_Test");
            _logger     = _go.AddComponent<GapLogger>();
            _policy     = _go.AddComponent<BehaviorPolicyLoader>();
            _dispatcher = _go.AddComponent<ActionDispatcher>();
            _controller = _go.AddComponent<AvatarController>();

            _tempPath = Path.Combine(
                Path.GetTempPath(), $"intg_test_{System.Guid.NewGuid():N}.jsonl");
            _logger.SetLogPathForTest(_tempPath);
            _logger.SetEnabled(true);
            _logger.ResetCountForTest();
        }

        [TearDown]
        public void TearDown()
        {
            if (File.Exists(_tempPath)) File.Delete(_tempPath);
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        private static string IntentJson(string intent, string fallback = "nod", string ctx = "{}")
            => $"{{\"id\":\"i1\",\"ts\":\"2025-01-01T00:00:00Z\"," +
               $"\"cmd\":\"avatar_intent\"," +
               $"\"params\":{{\"intent\":\"{intent}\"," +
               $"\"fallback\":\"{fallback}\"," +
               $"\"context_json\":\"{ctx}\"}}}}";

        private static string EventJson(string evtName = "superchat")
            => $"{{\"id\":\"e1\",\"ts\":\"2025-01-01T00:00:00Z\"," +
               $"\"cmd\":\"avatar_event\"," +
               $"\"params\":{{\"event\":\"{evtName}\",\"intensity\":1.0}}}}";

        private static System.Collections.Generic.Dictionary<string, BehaviorEntry> HitPolicy()
        {
            return new System.Collections.Generic.Dictionary<string, BehaviorEntry>
            {
                ["known_intent"] = new BehaviorEntry { cmd = "avatar_update", gesture = "wave", priority = 1 },
            };
        }

        // ── Tests ─────────────────────────────────────────────────────────────

        // [TC-INTG-01] avatar_intent メッセージがAvatarControllerを通してExecutedになる
        [UnityTest]
        public IEnumerator IntentMessage_KnownIntent_DispatchesExecuted()
        {
            _policy.InjectForTest(HitPolicy());
            DispatchResult capturedResult = default;
            _dispatcher.OnDispatched += r => capturedResult = r;

            _controller.HandleMessage(IntentJson("known_intent"));
            yield return null;

            Assert.AreEqual(DispatchResult.Executed, capturedResult,
                "Known intent must return Executed via full pipeline");
        }

        // [TC-INTG-02] 未知インテントでGapEntryが記録される (GapCountThisSession == 1)
        [UnityTest]
        public IEnumerator IntentMessage_UnknownIntent_RecordsGap()
        {
            _policy.InjectForTest(new System.Collections.Generic.Dictionary<string, BehaviorEntry>());

            _controller.HandleMessage(IntentJson("gesture_new_unknown", fallback: ""));
            yield return null;

            Assert.AreEqual(1, _logger.GapCountThisSession,
                "One gap must be logged for an unknown intent");
        }

        // [TC-INTG-03] 記録されたGapEntryに正しいintent名が含まれる
        [UnityTest]
        public IEnumerator IntentMessage_UnknownIntent_GapEntryContainsIntentName()
        {
            _policy.InjectForTest(new System.Collections.Generic.Dictionary<string, BehaviorEntry>());

            _controller.HandleMessage(IntentJson("gesture_unique_intent", fallback: ""));
            yield return null;

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("gesture_unique_intent", content,
                "Logged GapEntry must contain the intent name");
        }

        // [TC-INTG-04] gesture_* インテントのGapEntryのgap_categoryがmissing_motion
        [UnityTest]
        public IEnumerator IntentMessage_GestureIntent_GapCategoryIsMissingMotion()
        {
            _policy.InjectForTest(new System.Collections.Generic.Dictionary<string, BehaviorEntry>());

            _controller.HandleMessage(IntentJson("gesture_dance", fallback: ""));
            yield return null;

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"missing_motion\"", content,
                "gesture_* gap_category must be missing_motion");
        }

        // [TC-INTG-05] 記録されたGapEntryのtriggerが "avatar_intent_ws"
        [UnityTest]
        public IEnumerator IntentMessage_GapEntry_TriggerIsAvatarIntentWs()
        {
            _policy.InjectForTest(new System.Collections.Generic.Dictionary<string, BehaviorEntry>());

            _controller.HandleMessage(IntentJson("unknown_any", fallback: ""));
            yield return null;

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"avatar_intent_ws\"", content,
                "GapEntry.trigger must be 'avatar_intent_ws'");
        }

        // [TC-INTG-06] avatar_event メッセージはGapを記録しない
        [UnityTest]
        public IEnumerator EventMessage_DoesNotRecordGap()
        {
            _controller.HandleMessage(EventJson("superchat"));
            yield return null;

            Assert.AreEqual(0, _logger.GapCountThisSession,
                "avatar_event must not record a Gap");
        }
    }
}
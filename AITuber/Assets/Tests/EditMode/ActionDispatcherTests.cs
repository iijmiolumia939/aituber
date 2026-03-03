// ActionDispatcherTests.cs
// EditMode tests for ActionDispatcher.Dispatch.
// TC-ADSP-01 ~ TC-ADSP-15
//
// Coverage:
//   ADSP-01  Policy hit (exact) → Executed
//   ADSP-02  Policy miss → Skipped when no fallback
//   ADSP-03  Policy miss with fallback → FallbackExecuted
//   ADSP-04  Null params → Error
//   ADSP-05  Case-insensitive intent lookup → Executed
//   ADSP-06  CategorizeGap(gesture_*) → missing_motion
//   ADSP-07  CategorizeGap(emote_*) → missing_motion
//   ADSP-08  CategorizeGap(event_*) → missing_behavior
//   ADSP-09  context_json forwarded to GapEntry.intended_action.param
//   ADSP-10  currentState forwarded to GapEntry.current_state
//   ADSP-11  GapLogger.Instance=null → no crash (Skipped)
//   ADSP-12  BehaviorPolicyLoader.Instance=null → policy miss, Skipped
//   ADSP-13  intent=null in params → Skipped (no exception)
//   ADSP-14  GapEntry.gap_category matches CategorizeGap naming convention
//   ADSP-15  GapEntry.trigger = "avatar_intent_ws"

using System.IO;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using AITuber.Avatar;
using AITuber.Growth;

namespace AITuber.Tests
{
    public class ActionDispatcherTests
    {
        private GameObject             _go;
        private GapLogger              _logger;
        private BehaviorPolicyLoader   _policy;
        private ActionDispatcher       _dispatcher;
        private string                 _tempPath;

        [SetUp]
        public void SetUp()
        {
            // Force-clear singleton refs (handles deferred Destroy edge cases)
            GapLogger.ClearInstanceForTest();
            BehaviorPolicyLoader.ClearInstanceForTest();
            ActionDispatcher.ClearInstanceForTest();
            // Also destroy any lingering GameObject instances
            if (GapLogger.Instance != null)
                UnityEngine.Object.DestroyImmediate(GapLogger.Instance.gameObject);
            if (BehaviorPolicyLoader.Instance != null)
                UnityEngine.Object.DestroyImmediate(BehaviorPolicyLoader.Instance.gameObject);
            if (ActionDispatcher.Instance != null)
                UnityEngine.Object.DestroyImmediate(ActionDispatcher.Instance.gameObject);

            _go         = new GameObject("AD_Test");
            _logger     = _go.AddComponent<GapLogger>();
            _policy     = _go.AddComponent<BehaviorPolicyLoader>();
            _dispatcher = _go.AddComponent<ActionDispatcher>();

            _tempPath = Path.Combine(
                Path.GetTempPath(), $"adsp_test_{System.Guid.NewGuid():N}.jsonl");
            _logger.SetLogPathForTest(_tempPath);  // also ensures _streamId is set
            _logger.SetEnabled(true);
            _logger.ResetCountForTest();

            // Explicitly inject co-located dependencies into dispatcher.
            // This is necessary because Awake/GetComponent may not run in all
            // EditMode test contexts; the helpers bypass singleton lookup entirely.
            _dispatcher.SetGapLoggerForTest(_logger);
            _dispatcher.SetPolicyLoaderForTest(_policy);
        }

        [TearDown]
        public void TearDown()
        {
            if (File.Exists(_tempPath)) File.Delete(_tempPath);
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        private static Dictionary<string, BehaviorEntry> PolicyWith(string intent, BehaviorEntry entry)
            => new Dictionary<string, BehaviorEntry> { { intent.ToLowerInvariant(), entry } };

        private static BehaviorEntry MakeEntry(string gesture = "nod")
            => new BehaviorEntry { cmd = "avatar_update", gesture = gesture, priority = 1 };

        private static AvatarIntentParams Params(string intent, string fallback = "nod",
                                                  string ctx = null)
            => new AvatarIntentParams
            {
                intent       = intent,
                fallback     = fallback ?? "",
                context_json = ctx ?? "",
            };

        // ── Tests ─────────────────────────────────────────────────────────────

        // [TC-ADSP-01] ポリシーにヒットした場合 Executed が返る
        [Test]
        public void Dispatch_PolicyHit_ReturnsExecuted()
        {
            _policy.InjectForTest(PolicyWith("test_intent", MakeEntry()));
            var result = _dispatcher.Dispatch(Params("test_intent"));
            Assert.AreEqual(DispatchResult.Executed, result);
        }

        // [TC-ADSP-02] ポリシーミスでフォールバック無し → Skipped
        [Test]
        public void Dispatch_PolicyMiss_NoFallback_ReturnsSkipped()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            var result = _dispatcher.Dispatch(Params("unknown_intent", fallback: ""));
            Assert.AreEqual(DispatchResult.Skipped, result);
        }

        // [TC-ADSP-03] ポリシーミスでフォールバックあり → FallbackExecuted
        [Test]
        public void Dispatch_PolicyMiss_WithFallback_ReturnsFallbackExecuted()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            var result = _dispatcher.Dispatch(Params("unknown_intent", fallback: "nod"));
            Assert.AreEqual(DispatchResult.FallbackExecuted, result);
        }

        // [TC-ADSP-04] null params → Error、例外なし
        [Test]
        public void Dispatch_NullParams_ReturnsError()
        {
            DispatchResult result = default;
            Assert.DoesNotThrow(() => result = _dispatcher.Dispatch(null));
            Assert.AreEqual(DispatchResult.Error, result);
        }

        // [TC-ADSP-05] case-insensitive なインテント検索でヒット → Executed
        [Test]
        public void Dispatch_CaseInsensitiveIntent_ReturnsExecuted()
        {
            _policy.InjectForTest(PolicyWith("case_intent", MakeEntry()));
            var result = _dispatcher.Dispatch(Params("CASE_INTENT"));
            Assert.AreEqual(DispatchResult.Executed, result);
        }

        // [TC-ADSP-06] gesture_* → gap_category = "missing_motion"
        [Test]
        public void CategorizeGap_GesturePrefix_ReturnsMissingMotion()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("gesture_dance", fallback: ""));

            string line = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"missing_motion\"", line);
        }

        // [TC-ADSP-07] emote_* → gap_category = "missing_motion"
        [Test]
        public void CategorizeGap_EmotePrefix_ReturnsMissingMotion()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("emote_happy", fallback: ""));

            string line = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"missing_motion\"", line);
        }

        // [TC-ADSP-08] event_* → gap_category = "missing_behavior"
        [Test]
        public void CategorizeGap_EventPrefix_ReturnsMissingBehavior()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("event_superchat", fallback: ""));

            string line = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"missing_behavior\"", line);
        }

        // [TC-ADSP-09] context_json が GapEntry.intended_action.param に転送される
        [Test]
        public void Dispatch_ContextJson_ForwardedToGapEntry()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("unknown_intent", ctx: "{\"value\":42}"));

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("{\\\"value\\\":42}", content,
                "context_json must appear in intended_action.param");
        }

        // [TC-ADSP-10] currentState が GapEntry.current_state に転送される
        [Test]
        public void Dispatch_CurrentState_ForwardedToGapEntry()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("unknown_intent"), currentState: "idle_standing");

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"idle_standing\"", content,
                "currentState must appear in GapEntry.current_state");
        }

        // [TC-ADSP-11] GapLogger.Instance=null でも Skipped かつクラッシュしない
        [Test]
        public void Dispatch_GapLoggerNull_NoCrashReturnsSkipped()
        {
            // Destroy only GapLogger component; dispatcher and policyLoader survive
            UnityEngine.Object.DestroyImmediate(_logger);

            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());

            DispatchResult result = default;
            Assert.DoesNotThrow(() => result = _dispatcher.Dispatch(Params("x_intent", fallback: "")));
            // Result is Skipped (no policy hit, no fallback)
            Assert.AreEqual(DispatchResult.Skipped, result);
        }

        // [TC-ADSP-12] BehaviorPolicyLoader.Instance=null → policy miss → Skipped (フォールバック無し)
        [Test]
        public void Dispatch_PolicyLoaderNull_TreatedAsPolicyMiss()
        {
            // Destroy only policyLoader; GapLogger survives
            UnityEngine.Object.DestroyImmediate(_policy);

            DispatchResult result = default;
            Assert.DoesNotThrow(() => result = _dispatcher.Dispatch(Params("x_intent", fallback: "")));
            Assert.AreEqual(DispatchResult.Skipped, result);
        }

        // [TC-ADSP-13] AvatarIntentParams.intent = null → Skipped（例外なし）
        [Test]
        public void Dispatch_NullIntent_ReturnsSkipped()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            DispatchResult result = default;
            Assert.DoesNotThrow(() => result = _dispatcher.Dispatch(Params(null, fallback: "")));
            Assert.AreEqual(DispatchResult.Skipped, result);
        }

        // [TC-ADSP-14] 書き込まれたGapEntryのgap_categoryがCategorizeGap命名規則に一致
        [Test]
        public void Dispatch_GapCategoryMatchesNamingConvention()
        {
            var validCategories = new[]
            {
                "missing_motion", "missing_behavior", "missing_integration",
                "environment_limit", "capability_limit", "unknown",
            };

            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("unknown_genre_intent", fallback: ""));

            string content = File.ReadAllText(_tempPath);
            bool matched = false;
            foreach (var cat in validCategories)
                if (content.Contains($"\"{cat}\"")) { matched = true; break; }

            Assert.IsTrue(matched, $"gap_category not in valid set. Content: {content}");
        }

        // [TC-ADSP-15] GapEntry.trigger が "avatar_intent_ws" で固定されている
        [Test]
        public void Dispatch_GapEntry_TriggerIsAvatarIntentWs()
        {
            _policy.InjectForTest(new Dictionary<string, BehaviorEntry>());
            _dispatcher.Dispatch(Params("trigger_test", fallback: ""));

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"avatar_intent_ws\"", content,
                "GapEntry.trigger must be 'avatar_intent_ws'");
        }
    }
}
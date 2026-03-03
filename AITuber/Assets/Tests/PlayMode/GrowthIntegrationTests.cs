// GrowthIntegrationTests.cs
// PlayMode integration tests for the Growth pipeline:
//   WebSocket message → AvatarController → ActionDispatcher → GapLogger
//
// TC-INTG-01 ~ TC-INTG-03

using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using AITuber.Avatar;
using AITuber.Growth;

namespace AITuber.Tests
{
    public class GrowthIntegrationTests
    {
        private GameObject _root;
        private AvatarController _controller;
        private ActionDispatcher _dispatcher;
        private GapLogger _logger;
        private BehaviorPolicyLoader _policyLoader;
        private string _tempLogPath;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            _root = new GameObject("IntgRoot");

            // Add in dependency order (Awake fires in AddComponent order)
            _logger       = _root.AddComponent<GapLogger>();
            _policyLoader = _root.AddComponent<BehaviorPolicyLoader>();
            _dispatcher   = _root.AddComponent<ActionDispatcher>();
            _controller   = _root.AddComponent<AvatarController>();

            _tempLogPath = Path.Combine(Path.GetTempPath(), $"intg_{Guid.NewGuid():N}.jsonl");
            _logger.SetLogPathForTest(_tempLogPath);
            _logger.SetEnabled(true);
            _logger.ResetCountForTest();

            // Start with empty policy (all intents are unknown → gaps)
            _policyLoader.InjectForTest(new Dictionary<string, BehaviorEntry>());

            yield return null; // let Awake/Start finish
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            if (File.Exists(_tempLogPath)) File.Delete(_tempLogPath);
            UnityEngine.Object.Destroy(_root);
            yield return null;
        }

        // [TC-INTG-01] avatar_intentメッセージ → Gap記録 (エンドツーエンド)
        [UnityTest]
        public IEnumerator WsMessage_UnknownIntent_GapRecorded()
        {
            string json = "{\"cmd\":\"avatar_intent\",\"params\":{\"intent\":\"gesture_dance\",\"fallback\":\"nod\"}}";
            var (msg, typed) = AvatarMessageParser.Parse(json);
            _controller.HandleMessageForTest(msg, typed);

            yield return null;

            Assert.AreEqual(1, _logger.GapCountThisSession,
                "gesture_dance is not in policy → 1 gap should be recorded");

            string content = File.ReadAllText(_tempLogPath);
            StringAssert.Contains("\"gesture_dance\"", content);
            StringAssert.Contains("avatar_intent_ws", content);
        }

        // [TC-INTG-02] ポリシー登録済みintentはGapを記録しない
        [UnityTest]
        public IEnumerator WsMessage_KnownIntent_NoGapRecorded()
        {
            _policyLoader.InjectForTest(new Dictionary<string, BehaviorEntry>
            {
                ["nod_agreement"] = new BehaviorEntry
                {
                    intent  = "nod_agreement",
                    cmd     = "avatar_update",
                    gesture = "nod",
                },
            });

            string json = "{\"cmd\":\"avatar_intent\",\"params\":{\"intent\":\"nod_agreement\"}}";
            var (msg, typed) = AvatarMessageParser.Parse(json);
            _controller.HandleMessageForTest(msg, typed);

            yield return null;

            Assert.AreEqual(0, _logger.GapCountThisSession,
                "Policy hit → no gap should be recorded");
        }

        // [TC-INTG-03] avatar_update (既存コマンド) は Gapを記録せず正常動作する
        [UnityTest]
        public IEnumerator WsMessage_AvatarUpdate_WorksWithoutGap()
        {
            string json = "{\"cmd\":\"avatar_update\",\"params\":{\"emotion\":\"happy\",\"gesture\":\"wave\",\"look_target\":\"camera\",\"mouth_open\":0.0}}";
            var (msg, typed) = AvatarMessageParser.Parse(json);
            _controller.HandleMessageForTest(msg, typed);

            yield return null;

            Assert.AreEqual(0, _logger.GapCountThisSession,
                "avatar_update must not go through ActionDispatcher and must not log a gap");
        }
    }
}

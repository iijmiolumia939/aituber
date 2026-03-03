// GapLoggerTests.cs
// EditMode tests for GapLogger.Log / file output.
// TC-GLOG-01 ~ TC-GLOG-05

using System;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using AITuber.Growth;

namespace AITuber.Tests
{
    public class GapLoggerTests
    {
        private GameObject _go;
        private GapLogger _logger;
        private string _tempPath;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("GL_Test");
            _logger = _go.AddComponent<GapLogger>();
            // Redirect to temp file so tests don't pollute persistentDataPath
            _tempPath = Path.Combine(Path.GetTempPath(), $"gaplog_test_{Guid.NewGuid():N}.jsonl");
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

        private static GapEntry MakeEntry(string intentName, string fallback = "nod")
        {
            return new GapEntry
            {
                intended_action = new GapEntry.IntendedAction
                {
                    type = "intent",
                    name = intentName,
                },
                fallback_used = fallback,
                gap_category  = "missing_motion",
                context = new GapEntry.GapContext
                {
                    emotion     = "neutral",
                    look_target = "camera",
                },
            };
        }

        // [TC-GLOG-01] Log()を呼ぶとファイルにJSON行が書き出される
        [Test]
        public void Log_ValidEntry_WritesJsonLine()
        {
            _logger.Log(MakeEntry("point_at_screen", "nod"));

            Assert.IsTrue(File.Exists(_tempPath), "Log file must be created after Log()");
            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"point_at_screen\"", content);
            StringAssert.Contains("\"nod\"", content);
            StringAssert.Contains("\"missing_motion\"", content);
        }

        // [TC-GLOG-02] 複数回Log()を呼ぶと行が複数追記される
        [Test]
        public void Log_MultipleCalls_AppendsLines()
        {
            for (int i = 0; i < 3; i++)
                _logger.Log(MakeEntry($"intent_{i}"));

            string[] lines = File.ReadAllLines(_tempPath);
            Assert.AreEqual(3, lines.Length, "Each Log() call appends one line");
            Assert.AreEqual(3, _logger.GapCountThisSession);
        }

        // [TC-GLOG-03] timestampフィールドが自動設定される(UTC ISO 8601)
        [Test]
        public void Log_TimestampAutoSet_FormatIsISO8601()
        {
            _logger.Log(MakeEntry("test_intent"));

            string content = File.ReadAllText(_tempPath);
            // Expect something like "timestamp":"2026-03-03T..."
            StringAssert.Contains("\"timestamp\":\"20", content);
        }

        // [TC-GLOG-04] nullエントリを渡しても例外が発生しない
        [Test]
        public void Log_NullEntry_NoException()
        {
            Assert.DoesNotThrow(() => _logger.Log(null));
            Assert.AreEqual(0, _logger.GapCountThisSession, "Null entry must not increment counter");
        }

        // [TC-GLOG-05] enabled=falseの場合は書き込まれない
        [Test]
        public void Log_Disabled_NoWrite()
        {
            _logger.SetEnabled(false);
            _logger.Log(MakeEntry("some_intent"));

            Assert.IsFalse(File.Exists(_tempPath), "Disabled logger must not create file");
            Assert.AreEqual(0, _logger.GapCountThisSession);
        }
    }
}

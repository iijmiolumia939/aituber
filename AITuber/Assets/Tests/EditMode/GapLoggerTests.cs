// GapLoggerTests.cs
// EditMode tests for GapLogger.Log and related test helpers.
// TC-GLOG-01 ~ TC-GLOG-12
//
// Coverage:
//   GLOG-01  Valid entry writes one JSON line to file
//   GLOG-02  Multiple Log() calls append independent lines (count matches)
//   GLOG-03  Auto-set timestamp follows UTC ISO 8601 format
//   GLOG-04  Null entry: no exception, counter not incremented
//   GLOG-05  Disabled logger: no file write, counter stays zero
//   GLOG-06  Pre-set timestamp on entry is NOT overwritten by auto-fill
//   GLOG-07  Pre-set stream_id on entry is NOT overwritten by auto-fill
//   GLOG-08  Empty stream_id on entry is auto-filled from session identifier
//   GLOG-09  GapCountThisSession resets to 0 after ResetCountForTest()
//   GLOG-10  SetEnabled(true) after false resumes logging
//   GLOG-11  StreamId property returns the session identifier
//   GLOG-12  Log() appends to an existing file (does not overwrite)

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
        private GapLogger  _logger;
        private string     _tempPath;

        [SetUp]
        public void SetUp()
        {
            // Force-clear singleton refs and destroy any lingering instances
            GapLogger.ClearInstanceForTest();
            if (GapLogger.Instance != null)
                UnityEngine.Object.DestroyImmediate(GapLogger.Instance.gameObject);

            _go = new GameObject("GL_Test");
            _logger = _go.AddComponent<GapLogger>();
            _tempPath = Path.Combine(
                Path.GetTempPath(), $"gaplog_test_{Guid.NewGuid():N}.jsonl");
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

        // ── Factory ────────────────────────────────────────────────────────────

        private static GapEntry MakeEntry(
            string intentName, string fallback = "nod",
            string timestamp = null, string streamId = null)
        {
            var e = new GapEntry
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
            if (timestamp != null) e.timestamp  = timestamp;
            if (streamId  != null) e.stream_id  = streamId;
            return e;
        }

        // ── Tests ─────────────────────────────────────────────────────────────

        // [TC-GLOG-01] Log()を呼ぶとファイルにJSON行が書き出される
        [Test]
        public void Log_ValidEntry_WritesJsonLine()
        {
            _logger.Log(MakeEntry("point_at_screen", "nod"));
            _logger.FlushSync();

            Assert.IsTrue(File.Exists(_tempPath), "Log file must be created after Log()");
            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains("\"point_at_screen\"", content);
            StringAssert.Contains("\"nod\"",             content);
            StringAssert.Contains("\"missing_motion\"",  content);
        }

        // [TC-GLOG-02] 複数回Log()を呼ぶと行が複数追記され、カウンターも正確
        [Test]
        public void Log_MultipleCalls_AppendsLinesAndIncrementsCounter()
        {
            for (int i = 0; i < 3; i++)
                _logger.Log(MakeEntry($"intent_{i}"));
            _logger.FlushSync();

            string[] lines = File.ReadAllLines(_tempPath);
            Assert.AreEqual(3, lines.Length,               "3 lines in file");
            Assert.AreEqual(3, _logger.GapCountThisSession, "Counter reflects 3 calls");
        }

        // [TC-GLOG-03] timestampフィールドが自動設定される（UTC ISO 8601形式）
        [Test]
        public void Log_TimestampAutoSet_IsUTCISO8601()
        {
            _logger.Log(MakeEntry("test_intent"));
            _logger.FlushSync();

            string content = File.ReadAllText(_tempPath);
            // Expect e.g. "timestamp":"2026-03-03T14:30:00Z"
            StringAssert.Contains("\"timestamp\":\"20", content);
            StringAssert.Contains("Z\"",                content, "Timestamp must end with Z");
        }

        // [TC-GLOG-04] nullエントリを渡しても例外が発生せず、カウンターが増加しない
        [Test]
        public void Log_NullEntry_NoExceptionAndCounterUnchanged()
        {
            Assert.DoesNotThrow(() => _logger.Log(null));
            Assert.AreEqual(0, _logger.GapCountThisSession, "Null entry must not increment counter");
        }

        // [TC-GLOG-05] SetEnabled(false)の場合ファイルが作成されずカウンターが増加しない
        [Test]
        public void Log_Disabled_NoWriteAndNoCounterIncrement()
        {
            _logger.SetEnabled(false);
            _logger.Log(MakeEntry("some_intent"));

            Assert.IsFalse(File.Exists(_tempPath), "Disabled logger must not create file");
            Assert.AreEqual(0, _logger.GapCountThisSession, "Counter must stay zero");
        }

        // [TC-GLOG-06] エントリに既にtimestampが設定されている場合は上書きされない
        [Test]
        public void Log_PreSetTimestamp_NotOverwritten()
        {
            const string fixedTs = "2025-01-01T00:00:00Z";
            _logger.Log(MakeEntry("ts_test", timestamp: fixedTs));
            _logger.FlushSync();

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains(fixedTs, content, "Pre-set timestamp must be preserved");
        }

        // [TC-GLOG-07] エントリに既にstream_idが設定されている場合は上書きされない
        [Test]
        public void Log_PreSetStreamId_NotOverwritten()
        {
            const string fixedId = "custom_stream_xyz";
            _logger.Log(MakeEntry("sid_test", streamId: fixedId));
            _logger.FlushSync();

            string content = File.ReadAllText(_tempPath);
            StringAssert.Contains(fixedId, content, "Pre-set stream_id must be preserved");
        }

        // [TC-GLOG-08] エントリのstream_idが空の場合はセッションのstream_idで補完される
        [Test]
        public void Log_EmptyStreamId_AutoFilledFromSession()
        {
            // stream_id is not set → auto-fill expected
            _logger.Log(MakeEntry("auto_sid_test")); // streamId param omitted → ""
            _logger.FlushSync();

            string content = File.ReadAllText(_tempPath);
            // _logger.StreamId must appear in the entry
            StringAssert.Contains(_logger.StreamId, content,
                "Session stream_id must be injected when entry stream_id is empty");
        }

        // [TC-GLOG-09] ResetCountForTest()後のGapCountThisSessionは0になる
        [Test]
        public void ResetCountForTest_ResetsCounterToZero()
        {
            _logger.Log(MakeEntry("intent_a"));
            _logger.Log(MakeEntry("intent_b"));
            Assert.AreEqual(2, _logger.GapCountThisSession, "Precondition: 2 logged");

            _logger.ResetCountForTest();
            Assert.AreEqual(0, _logger.GapCountThisSession, "Counter must be 0 after reset");
        }

        // [TC-GLOG-10] SetEnabled(false)→SetEnabled(true)で再びログが書き出される
        [Test]
        public void SetEnabled_FalseThenTrue_ResumesLogging()
        {
            _logger.SetEnabled(false);
            _logger.Log(MakeEntry("skipped_intent"));

            _logger.SetEnabled(true);
            _logger.Log(MakeEntry("resumed_intent"));
            _logger.FlushSync();

            Assert.IsTrue(File.Exists(_tempPath), "File must exist after re-enable");
            string content = File.ReadAllText(_tempPath);
            StringAssert.DoesNotContain("\"skipped_intent\"", content, "Disabled entry absent");
            StringAssert.Contains("\"resumed_intent\"",       content, "Resumed entry present");
            Assert.AreEqual(1, _logger.GapCountThisSession, "Only resumed entry counted");
        }

        // [TC-GLOG-11] StreamIdプロパティがセッション識別子を返す
        [Test]
        public void StreamId_PropertyReturnsNonEmptyString()
        {
            Assert.IsFalse(string.IsNullOrEmpty(_logger.StreamId),
                "StreamId must not be null or empty after Awake");
        }

        // [TC-GLOG-12] 既存ファイルへのLog()は既存内容を消さずに追記する
        [Test]
        public void Log_ExistingFile_AppendsContent()
        {
            // Pre-populate the file
            File.WriteAllText(_tempPath, "{\"pre_existing\":true}\n");

            _logger.Log(MakeEntry("new_entry"));
            _logger.FlushSync();

            string[] lines = File.ReadAllLines(_tempPath);
            Assert.AreEqual(2, lines.Length, "Must have pre-existing + new line");
            StringAssert.Contains("pre_existing", lines[0], "Pre-existing line preserved");
            StringAssert.Contains("new_entry",    lines[1], "New entry appended");
        }
    }
}
// BehaviorPolicyLoaderTests.cs
// EditMode tests for BehaviorPolicyLoader.ParseYamlLines / Lookup / InjectForTest.
// TC-BPOL-01 ~ TC-BPOL-15
//
// Coverage:
//   BPOL-01  Valid single entry registered with correct fields
//   BPOL-02  Empty-intent entry silently skipped
//   BPOL-03  Lookup(null/empty/unknown) returns null, no exception
//   BPOL-04  Multiple entries all registered independently
//   BPOL-05  '#' comment lines not counted as entries
//   BPOL-06  intensity parsed as invariant-culture float
//   BPOL-07  Lookup is case-insensitive
//   BPOL-08  Duplicate intent: last definition wins
//   BPOL-09  Inline trailing " #comment" stripped from values
//   BPOL-10  Null lines array: no exception, policy cleared
//   BPOL-11  All fields (emotion/look_target/event/priority/notes) parsed
//   BPOL-12  Unknown/future keys silently ignored
//   BPOL-13  InjectForTest replaces policy completely
//   BPOL-14  InjectForTest(null) clears policy
//   BPOL-15  ParseYamlLines called twice overwrites previous policy

using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using AITuber.Growth;

namespace AITuber.Tests
{
    public class BehaviorPolicyLoaderTests
    {
        private GameObject _go;
        private BehaviorPolicyLoader _loader;

        [SetUp]
        public void SetUp()
        {
            BehaviorPolicyLoader.ClearInstanceForTest();
            if (BehaviorPolicyLoader.Instance != null)
                UnityEngine.Object.DestroyImmediate(BehaviorPolicyLoader.Instance.gameObject);

            _go = new GameObject("BPL_Test");
            _loader = _go.AddComponent<BehaviorPolicyLoader>();
            _loader.InjectForTest(new Dictionary<string, BehaviorEntry>());
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_go);
        }

        private static string[] L(params string[] lines) => lines;

        // [TC-BPOL-01] 正常な単一エントリがポリシーに登録され各フィールドが正確
        [Test]
        public void ParseYamlLines_ValidEntry_RegistersEntry()
        {
            _loader.ParseYamlLines(L(
                "- intent: nod_agreement",
                "  cmd: avatar_update",
                "  gesture: nod",
                "  priority: 0"
            ));
            var e = _loader.Lookup("nod_agreement");
            Assert.IsNotNull(e, "Entry must be registered");
            Assert.AreEqual("avatar_update", e.cmd);
            Assert.AreEqual("nod", e.gesture);
        }

        // [TC-BPOL-02] intentフィールドが空のエントリはポリシーに追加されない
        [Test]
        public void ParseYamlLines_EmptyIntent_EntryIgnored()
        {
            _loader.ParseYamlLines(L(
                "- intent:",
                "  cmd: avatar_update",
                "  gesture: nod"
            ));
            Assert.AreEqual(0, _loader.Policy.Count, "Empty intent entry must be skipped");
        }

        // [TC-BPOL-03] Lookupにnull/空文字/未登録intentを渡した場合nullを返す（例外なし）
        [Test]
        public void Lookup_NullOrEmptyOrUnknown_ReturnsNull()
        {
            Assert.IsNull(_loader.Lookup(null),             "null -> null");
            Assert.IsNull(_loader.Lookup(""),               "empty -> null");
            Assert.IsNull(_loader.Lookup("no_such_intent"), "unknown -> null");
        }

        // [TC-BPOL-04] 複数エントリが全件登録され独立して取得可能
        [Test]
        public void ParseYamlLines_MultipleEntries_AllRegistered()
        {
            _loader.ParseYamlLines(L(
                "- intent: gesture_a",
                "  cmd: avatar_update",
                "  gesture: wave",
                "- intent: gesture_b",
                "  cmd: avatar_event",
                "  event: comment_read_start",
                "  intensity: 1.0"
            ));
            Assert.AreEqual(2, _loader.Policy.Count, "Both entries registered");
            Assert.IsNotNull(_loader.Lookup("gesture_a"));
            Assert.IsNotNull(_loader.Lookup("gesture_b"));
        }

        // [TC-BPOL-05] '#'で始まる行はエントリ数にカウントされない
        [Test]
        public void ParseYamlLines_CommentLines_Skipped()
        {
            _loader.ParseYamlLines(L(
                "# file comment",
                "- intent: nod_agreement",
                "  # inline comment line (whole line),",
                "  cmd: avatar_update",
                "  gesture: nod"
            ));
            Assert.AreEqual(1, _loader.Policy.Count, "Comment lines must not add entries");
        }

        // [TC-BPOL-06] intensityフィールドがinvariant-culture floatとして正しくパース
        [Test]
        public void ParseYamlLines_IntensityFloat_ParsedCorrectly()
        {
            _loader.ParseYamlLines(L(
                "- intent: look_at_comment",
                "  cmd: avatar_event",
                "  event: comment_read_start",
                "  intensity: 0.75"
            ));
            var e = _loader.Lookup("look_at_comment");
            Assert.IsNotNull(e);
            Assert.AreEqual(0.75f, e.intensity, 0.001f);
        }

        // [TC-BPOL-07] Lookupは大文字小文字を区別しない
        [Test]
        public void Lookup_DifferentCase_ReturnsEntry()
        {
            _loader.ParseYamlLines(L(
                "- intent: Nod_Agreement",
                "  cmd: avatar_update",
                "  gesture: nod"
            ));
            Assert.IsNotNull(_loader.Lookup("nod_agreement"), "lowercase works");
            Assert.IsNotNull(_loader.Lookup("NOD_AGREEMENT"), "uppercase works");
            Assert.IsNotNull(_loader.Lookup("Nod_Agreement"), "original case works");
        }

        // [TC-BPOL-08] 同一intentが2回定義された場合、後の定義が勝つ
        [Test]
        public void ParseYamlLines_DuplicateIntent_LastWins()
        {
            _loader.ParseYamlLines(L(
                "- intent: nod_agreement",
                "  cmd: avatar_update",
                "  gesture: first_gesture",
                "- intent: nod_agreement",
                "  cmd: avatar_update",
                "  gesture: second_gesture"
            ));
            Assert.AreEqual(1, _loader.Policy.Count, "Deduplicated to 1 entry");
            Assert.AreEqual("second_gesture", _loader.Lookup("nod_agreement").gesture, "Second wins");
        }

        // [TC-BPOL-09] 値の後ろの " #コメント" が除去される
        [Test]
        public void ParseYamlLines_InlineTrailingComment_Stripped()
        {
            _loader.ParseYamlLines(L(
                "- intent: nod_agreement # intent comment",
                "  cmd: avatar_update # cmd comment",
                "  gesture: nod # gesture comment"
            ));
            var e = _loader.Lookup("nod_agreement");
            Assert.IsNotNull(e, "Entry registered despite trailing comments");
            Assert.AreEqual("avatar_update", e.cmd,    "cmd: comment stripped");
            Assert.AreEqual("nod",           e.gesture, "gesture: comment stripped");
        }

        // [TC-BPOL-10] nullのlines配列を渡しても例外が発生せず、ポリシーが空になる
        [Test]
        public void ParseYamlLines_NullLines_NoExceptionAndEmptyPolicy()
        {
            _loader.InjectForTest(new Dictionary<string, BehaviorEntry>
            {
                ["dummy"] = new BehaviorEntry { intent = "dummy" }
            });
            Assert.DoesNotThrow(() => _loader.ParseYamlLines(null));
            Assert.AreEqual(0, _loader.Policy.Count, "Null lines clears policy");
        }

        // [TC-BPOL-11] 全フィールド（emotion/look_target/event/priority/notes）が正しくパース
        [Test]
        public void ParseYamlLines_FullEntry_AllFieldsParsed()
        {
            _loader.ParseYamlLines(L(
                "- intent: full_entry_test",
                "  cmd: avatar_event",
                "  emotion: happy",
                "  gesture: wave",
                "  look_target: comment",
                "  event: comment_read_start",
                "  intensity: 0.5",
                "  priority: 2",
                "  notes: A comprehensive test entry"
            ));
            var e = _loader.Lookup("full_entry_test");
            Assert.IsNotNull(e);
            Assert.AreEqual("avatar_event",            e.cmd);
            Assert.AreEqual("happy",                   e.emotion);
            Assert.AreEqual("wave",                    e.gesture);
            Assert.AreEqual("comment",                 e.look_target);
            Assert.AreEqual("comment_read_start",      e.@event);
            Assert.AreEqual(0.5f,                      e.intensity, 0.001f);
            Assert.AreEqual(2,                         e.priority);
            Assert.AreEqual("A comprehensive test entry", e.notes);
        }

        // [TC-BPOL-12] 未知のキーがあっても例外が発生せず、既知フィールドは正常にパース
        [Test]
        public void ParseYamlLines_UnknownKey_SilentlyIgnored()
        {
            _loader.ParseYamlLines(L(
                "- intent: future_intent",
                "  cmd: avatar_update",
                "  gesture: nod",
                "  future_key_v2: some_value",
                "  another_unknown: 42"
            ));
            var e = _loader.Lookup("future_intent");
            Assert.IsNotNull(e, "Entry with unknown keys must still register");
            Assert.AreEqual("nod", e.gesture, "Known field still parsed correctly");
        }

        // [TC-BPOL-13] InjectForTestでポリシーが完全に置き換えられる
        [Test]
        public void InjectForTest_ReplacesPolicyCompletely()
        {
            _loader.ParseYamlLines(L(
                "- intent: old_intent",
                "  cmd: avatar_update",
                "  gesture: nod"
            ));
            _loader.InjectForTest(new Dictionary<string, BehaviorEntry>
            {
                ["new_intent"] = new BehaviorEntry { intent = "new_intent", cmd = "avatar_event" }
            });
            Assert.AreEqual(1, _loader.Policy.Count);
            Assert.IsNull(_loader.Lookup("old_intent"),  "Old entry gone");
            Assert.IsNotNull(_loader.Lookup("new_intent"), "New entry present");
        }

        // [TC-BPOL-14] InjectForTest(null)を渡すとポリシーが空になる
        [Test]
        public void InjectForTest_Null_ClearsPolicy()
        {
            _loader.ParseYamlLines(L(
                "- intent: some_intent",
                "  cmd: avatar_update",
                "  gesture: nod"
            ));
            _loader.InjectForTest(null);
            Assert.AreEqual(0, _loader.Policy.Count, "Policy empty after null inject");
        }

        // [TC-BPOL-15] ParseYamlLinesを2回呼ぶと前回の結果が完全に上書きされる
        [Test]
        public void ParseYamlLines_CalledTwice_SecondCallOverwrites()
        {
            _loader.ParseYamlLines(L(
                "- intent: first_intent",
                "  cmd: avatar_update",
                "  gesture: nod"
            ));
            _loader.ParseYamlLines(L(
                "- intent: second_intent",
                "  cmd: avatar_update",
                "  gesture: wave",
                "- intent: third_intent",
                "  cmd: avatar_event",
                "  event: comment_read_start",
                "  intensity: 1.0"
            ));
            Assert.AreEqual(2, _loader.Policy.Count, "Second parse replaces first");
            Assert.IsNull(_loader.Lookup("first_intent"),     "First-parse entry removed");
            Assert.IsNotNull(_loader.Lookup("second_intent"), "Second entry present");
            Assert.IsNotNull(_loader.Lookup("third_intent"),  "Third entry present");
        }
    }
}
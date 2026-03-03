// BehaviorPolicyLoaderTests.cs
// EditMode tests for BehaviorPolicyLoader.ParseYamlLines / Lookup.
// TC-BPOL-01 ~ TC-BPOL-06

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
            _go = new GameObject("BPL_Test");
            _loader = _go.AddComponent<BehaviorPolicyLoader>();
            // Awake() runs automatically; it tries to Load() from StreamingAssets.
            // Inject empty policy so tests start from a clean state.
            _loader.InjectForTest(new Dictionary<string, BehaviorEntry>());
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // [TC-BPOL-01] 正常なYAML行列をパースするとentryが辞書に登録される
        [Test]
        public void ParseYamlLines_ValidEntry_RegistersEntry()
        {
            var lines = new[]
            {
                "- intent: nod_agreement",
                "  cmd: avatar_update",
                "  gesture: nod",
                "  priority: 0"
            };
            _loader.ParseYamlLines(lines);

            var entry = _loader.Lookup("nod_agreement");
            Assert.IsNotNull(entry, "Entry should be registered");
            Assert.AreEqual("nod", entry.gesture);
            Assert.AreEqual("avatar_update", entry.cmd);
        }

        // [TC-BPOL-02] intentフィールドが空のエントリは無視される
        [Test]
        public void ParseYamlLines_EmptyIntent_Ignored()
        {
            var lines = new[]
            {
                "- intent:",
                "  cmd: avatar_update",
                "  gesture: nod"
            };
            _loader.ParseYamlLines(lines);

            Assert.AreEqual(0, _loader.Policy.Count, "Entry with empty intent must be skipped");
        }

        // [TC-BPOL-03] 未登録intentのLookupはnullを返す（例外なし）
        [Test]
        public void Lookup_UnregisteredIntent_ReturnsNull()
        {
            Assert.IsNull(_loader.Lookup("no_such_intent"), "Unknown intent → null");
            Assert.IsNull(_loader.Lookup(""),               "Empty intent → null");
            Assert.IsNull(_loader.Lookup(null),             "Null intent → null");
        }

        // [TC-BPOL-04] 複数エントリが正しく登録される
        [Test]
        public void ParseYamlLines_MultipleEntries_AllRegistered()
        {
            var lines = new[]
            {
                "- intent: gesture_a",
                "  cmd: avatar_update",
                "  gesture: wave",
                "- intent: gesture_b",
                "  cmd: avatar_event",
                "  event: comment_read_start",
                "  intensity: 1.0"
            };
            _loader.ParseYamlLines(lines);

            Assert.AreEqual(2, _loader.Policy.Count, "Both entries should be registered");
            Assert.IsNotNull(_loader.Lookup("gesture_a"));
            Assert.IsNotNull(_loader.Lookup("gesture_b"));
        }

        // [TC-BPOL-05] #コメント行はスキップされる
        [Test]
        public void ParseYamlLines_CommentLines_Skipped()
        {
            var lines = new[]
            {
                "# ファイルコメント",
                "- intent: nod_agreement",
                "  # インラインコメント",
                "  cmd: avatar_update",
                "  gesture: nod"
            };
            _loader.ParseYamlLines(lines);

            Assert.AreEqual(1, _loader.Policy.Count, "Comment lines must not create entries");
        }

        // [TC-BPOL-06] intensityフィールドがfloatとして正しくパースされる
        [Test]
        public void ParseYamlLines_IntensityFloat_Parsed()
        {
            var lines = new[]
            {
                "- intent: look_at_comment",
                "  cmd: avatar_event",
                "  event: comment_read_start",
                "  intensity: 0.75"
            };
            _loader.ParseYamlLines(lines);

            var entry = _loader.Lookup("look_at_comment");
            Assert.IsNotNull(entry);
            Assert.AreEqual(0.75f, entry.intensity, 0.001f, "Intensity must be parsed as float");
        }
    }
}

// AvatarMessageParserTests.cs
// EditMode tests for AvatarMessageParser.Parse with the new avatar_intent command
// and backward-compatibility for existing commands.
// TC-MSG-01 ~ TC-MSG-05

using NUnit.Framework;
using AITuber.Avatar;

namespace AITuber.Tests
{
    public class AvatarMessageParserTests
    {
        // [TC-MSG-01] avatar_intentコマンドがAvatarIntentParamsにパースされる
        [Test]
        public void Parse_AvatarIntent_ReturnsAvatarIntentParams()
        {
            string json = "{\"cmd\":\"avatar_intent\",\"params\":{\"intent\":\"point_at_screen\",\"fallback\":\"nod\"}}";
            var (msg, typed) = AvatarMessageParser.Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("avatar_intent", msg.cmd);
            Assert.IsInstanceOf<AvatarIntentParams>(typed);

            var p = (AvatarIntentParams)typed;
            Assert.AreEqual("point_at_screen", p.intent);
            Assert.AreEqual("nod", p.fallback);
        }

        // [TC-MSG-02] intentフィールド省略でも例外が発生しない (デフォルト値になる)
        [Test]
        public void Parse_AvatarIntent_MissingFields_NoException()
        {
            string json = "{\"cmd\":\"avatar_intent\",\"params\":{}}";
            (AvatarMessage msg, object typed) result = default;
            Assert.DoesNotThrow(() => result = AvatarMessageParser.Parse(json));
            Assert.IsNotNull(result.msg);
            Assert.IsInstanceOf<AvatarIntentParams>(result.typed);

            var p = (AvatarIntentParams)result.typed;
            // Should fall back to default field values
            Assert.IsNotNull(p.intent);
            Assert.IsNotNull(p.fallback);
        }

        // [TC-MSG-03] context_jsonフィールドも正しくパースされる
        [Test]
        public void Parse_AvatarIntent_ContextJson_Parsed()
        {
            string json = "{\"cmd\":\"avatar_intent\",\"params\":{\"intent\":\"celebrate_milestone\",\"fallback\":\"wave\",\"context_json\":\"{\\\"target\\\":\\\"superchat\\\"}\"}}";
            var (_, typed) = AvatarMessageParser.Parse(json);

            Assert.IsInstanceOf<AvatarIntentParams>(typed);
            var p = (AvatarIntentParams)typed;
            Assert.AreEqual("celebrate_milestone", p.intent);
            Assert.AreEqual("wave", p.fallback);
            StringAssert.Contains("superchat", p.context_json);
        }

        // [TC-MSG-04] 既存のavatar_updateコマンドが後方互換を維持する
        [Test]
        public void Parse_AvatarUpdate_BackwardCompatible()
        {
            string json = "{\"cmd\":\"avatar_update\",\"params\":{\"emotion\":\"happy\",\"gesture\":\"wave\"}}";
            var (msg, typed) = AvatarMessageParser.Parse(json);

            Assert.AreEqual("avatar_update", msg.cmd);
            Assert.IsInstanceOf<AvatarUpdateParams>(typed);
            var p = (AvatarUpdateParams)typed;
            Assert.AreEqual("happy", p.emotion);
            Assert.AreEqual("wave", p.gesture);
        }

        // [TC-MSG-05] 不正JSONの場合はnullを返す（例外なし）
        [Test]
        public void Parse_InvalidJson_ReturnsNull_NoException()
        {
            (AvatarMessage msg, object typed) result = default;
            Assert.DoesNotThrow(() => result = AvatarMessageParser.Parse("not_json{{{"));
            Assert.IsNull(result.msg);
        }
    }
}

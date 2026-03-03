// AvatarMessageParserTests.cs
// EditMode tests for AvatarMessageParser.Parse (all message types).
// TC-MSG-01 ~ TC-MSG-13
//
// Coverage:
//   MSG-01  avatar_update  → AvatarUpdateParams
//   MSG-02  avatar_intent  → AvatarIntentParams (intent/fallback/context_json)
//   MSG-03  capabilities   → CapabilitiesParams (not null)
//   MSG-04  room_change    → RoomChangeParams
//   MSG-05  avatar_viseme  → AvatarVisemeParams (viseme_set, strength)
//   MSG-06  avatar_event   → AvatarEventParams  (event, intensity)
//   MSG-07  avatar_reset   → typed=null, msg.cmd="avatar_reset"
//   MSG-08  avatar_config  → AvatarConfigParams (mouth_sensitivity, idle_motion)
//   MSG-09  Null input     → (null,null), no exception
//   MSG-10  Empty string   → (null,null), no exception
//   MSG-11  Unknown cmd    → msg!=null, typed=null
//   MSG-12  id / ts fields parsed correctly
//   MSG-13  avatar_intent all fields (intent/fallback/context_json) accessible

using NUnit.Framework;
using AITuber.Avatar;

namespace AITuber.Tests
{
    public class AvatarMessageParserTests
    {
        // ── Helpers ───────────────────────────────────────────────────────────

        private static (AvatarMessage msg, object typed) Parse(string json)
            => AvatarMessageParser.Parse(json);

        private static string BuildJson(string inner,
            string id = "id1", string ts = "2025-01-01T00:00:00Z")
            => $"{{\"id\":\"{id}\",\"ts\":\"{ts}\",{inner}}}";

        // ── Tests ─────────────────────────────────────────────────────────────

        // [TC-MSG-01] avatar_update → AvatarUpdateParams にパースされる
        [Test]
        public void Parse_AvatarUpdate_ReturnsAvatarUpdateParams()
        {
            string json = BuildJson(
                "\"cmd\":\"avatar_update\"," +
                "\"params\":{\"emotion\":\"joy\",\"look_target\":\"camera\"}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg, "msg must not be null");
            Assert.AreEqual("avatar_update", msg.cmd);
            Assert.IsInstanceOf<AvatarUpdateParams>(typed);
            var p = (AvatarUpdateParams)typed;
            Assert.AreEqual("joy",    p.emotion);
            Assert.AreEqual("camera", p.look_target);
        }

        // [TC-MSG-02] avatar_intent → AvatarIntentParams にパースされる
        [Test]
        public void Parse_AvatarIntent_ReturnsAvatarIntentParams()
        {
            string json = BuildJson(
                "\"cmd\":\"avatar_intent\"," +
                "\"params\":{\"intent\":\"gesture_wave\",\"fallback\":\"nod\"," +
                "\"context_json\":\"{\\\"key\\\":\\\"val\\\"}\"}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("avatar_intent", msg.cmd);
            Assert.IsInstanceOf<AvatarIntentParams>(typed);
            var p = (AvatarIntentParams)typed;
            Assert.AreEqual("gesture_wave", p.intent);
            Assert.AreEqual("nod",          p.fallback);
            StringAssert.Contains("key",    p.context_json);
        }

        // [TC-MSG-03] capabilities → CapabilitiesParams にパースされる
        [Test]
        public void Parse_Capabilities_ReturnsCapabilitiesParams()
        {
            string json = BuildJson(
                "\"cmd\":\"capabilities\"," +
                "\"params\":{\"mouth_open\":true,\"viseme\":false}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("capabilities", msg.cmd);
            Assert.IsInstanceOf<CapabilitiesParams>(typed);
            var p = (CapabilitiesParams)typed;
            Assert.IsTrue(p.mouth_open);
            Assert.IsFalse(p.viseme);
        }

        // [TC-MSG-04] room_change → RoomChangeParams にパースされる
        [Test]
        public void Parse_RoomChange_ReturnsRoomChangeParams()
        {
            string json = BuildJson(
                "\"cmd\":\"room_change\",\"params\":{\"room_id\":\"room_42\"}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("room_change", msg.cmd);
            Assert.IsInstanceOf<RoomChangeParams>(typed);
            Assert.AreEqual("room_42", ((RoomChangeParams)typed).room_id);
        }

        // [TC-MSG-05] avatar_viseme → AvatarVisemeParams にパースされる (viseme_set / strength)
        [Test]
        public void Parse_AvatarViseme_ReturnsAvatarVisemeParams()
        {
            string json = BuildJson(
                "\"cmd\":\"avatar_viseme\"," +
                "\"params\":{\"viseme_set\":\"jp_basic_8\",\"strength\":0.75}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("avatar_viseme", msg.cmd);
            Assert.IsInstanceOf<AvatarVisemeParams>(typed);
            var p = (AvatarVisemeParams)typed;
            Assert.AreEqual("jp_basic_8", p.viseme_set);
            Assert.AreEqual(0.75f, p.strength, 0.001f);
        }

        // [TC-MSG-06] avatar_event → AvatarEventParams にパースされる
        [Test]
        public void Parse_AvatarEvent_ReturnsAvatarEventParams()
        {
            string json = BuildJson(
                "\"cmd\":\"avatar_event\"," +
                "\"params\":{\"event\":\"superchat\",\"intensity\":1.0}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("avatar_event", msg.cmd);
            Assert.IsInstanceOf<AvatarEventParams>(typed);
            var p = (AvatarEventParams)typed;
            Assert.AreEqual("superchat", p.@event);
            Assert.AreEqual(1.0f, p.intensity, 0.001f);
        }

        // [TC-MSG-07] avatar_reset → typed=null, msg.cmd = "avatar_reset"
        [Test]
        public void Parse_AvatarReset_TypedIsNull()
        {
            string json = BuildJson("\"cmd\":\"avatar_reset\",\"params\":{}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("avatar_reset", msg.cmd);
            Assert.IsNull(typed, "avatar_reset has no typed params");
        }

        // [TC-MSG-08] avatar_config → AvatarConfigParams にパースされる
        [Test]
        public void Parse_AvatarConfig_ReturnsAvatarConfigParams()
        {
            string json = BuildJson(
                "\"cmd\":\"avatar_config\"," +
                "\"params\":{\"mouth_sensitivity\":0.5,\"idle_motion\":\"slow\"}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual("avatar_config", msg.cmd);
            Assert.IsInstanceOf<AvatarConfigParams>(typed);
            var p = (AvatarConfigParams)typed;
            Assert.AreEqual(0.5f,   p.mouth_sensitivity, 0.001f);
            Assert.AreEqual("slow", p.idle_motion);
        }

        // [TC-MSG-09] null JSON → (null,null)、例外なし
        [Test]
        public void Parse_NullInput_ReturnsNullTupleNoException()
        {
            (AvatarMessage msg, object typed) result = default;
            Assert.DoesNotThrow(() => result = Parse(null));
            Assert.IsNull(result.msg,   "null input: msg must be null");
            Assert.IsNull(result.typed, "null input: typed must be null");
        }

        // [TC-MSG-10] 空文字列 → (null,null)、例外なし
        [Test]
        public void Parse_EmptyString_ReturnsNullTupleNoException()
        {
            (AvatarMessage msg, object typed) result = default;
            Assert.DoesNotThrow(() => result = Parse(""));
            Assert.IsNull(result.msg,   "empty string: msg must be null");
            Assert.IsNull(result.typed, "empty string: typed must be null");
        }

        // [TC-MSG-11] 未知のcmd → msg!=null で typed=null
        [Test]
        public void Parse_UnknownCmd_MsgNotNullTypedNull()
        {
            string json = BuildJson("\"cmd\":\"unknown_xyz\",\"params\":{}");

            var (msg, typed) = Parse(json);

            Assert.IsNotNull(msg,  "Unknown cmd must still return a msg");
            Assert.IsNull(typed,   "Unknown cmd must have null typed params");
            Assert.AreEqual("unknown_xyz", msg.cmd);
        }

        // [TC-MSG-12] id と ts フィールドが正しくパースされる
        [Test]
        public void Parse_IdAndTsFields_ParsedCorrectly()
        {
            const string expectId = "abc123";
            const string expectTs = "2026-06-15T12:00:00Z";
            string json = BuildJson(
                "\"cmd\":\"capabilities\",\"params\":{}",
                id: expectId, ts: expectTs);

            var (msg, _) = Parse(json);

            Assert.IsNotNull(msg);
            Assert.AreEqual(expectId, msg.id);
            Assert.AreEqual(expectTs, msg.ts);
        }

        // [TC-MSG-13] avatar_intent の intent / fallback / context_json が全て取得できる
        [Test]
        public void Parse_AvatarIntent_AllFieldsParsed()
        {
            string json = BuildJson(
                "\"cmd\":\"avatar_intent\"," +
                "\"params\":{\"intent\":\"emote_excited\"," +
                "\"fallback\":\"wave\",\"context_json\":\"{}\"}");

            var (_, typed) = Parse(json);
            var p = typed as AvatarIntentParams;

            Assert.IsNotNull(p);
            Assert.AreEqual("emote_excited", p.intent);
            Assert.AreEqual("wave",          p.fallback);
            Assert.AreEqual("{}",            p.context_json);
        }
    }
}
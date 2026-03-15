// WsMsgPackTests.cs
// EditMode unit tests for MsgPackDecoder.
// TC-MSGPACK-C#-01 ~ TC-MSGPACK-C#-04
//
// Coverage:
//   MSGPACK-C#-01  fixmap + fixstr       → JSON object string
//   MSGPACK-C#-02  float32 value         → JSON float with precision ≤ 0.001
//   MSGPACK-C#-03  nested map            → nested JSON object
//   MSGPACK-C#-04  bool true + null nil  → JSON true/null literals
//
// SRS refs: FR-PERF-01
// Issue: #61

using NUnit.Framework;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode tests for <see cref="MsgPackDecoder"/>.
    /// TC-MSGPACK-C#-01 ~ TC-MSGPACK-C#-04
    /// FR-PERF-01 / Issue #61
    /// </summary>
    public class WsMsgPackTests
    {
        // ── TC-MSGPACK-C#-01 ─────────────────────────────────────────────────

        [Test]
        public void Decode_FixmapFixstr_ProducesJsonObject()
        {
            // {"cmd":"test"}
            // 81  a3 63 6d 64  a4 74 65 73 74
            byte[] data =
            {
                0x81,                               // fixmap, count=1
                0xa3, 0x63, 0x6d, 0x64,            // fixstr(3) "cmd"
                0xa4, 0x74, 0x65, 0x73, 0x74,      // fixstr(4) "test"
            };

            string json = MsgPackDecoder.ToJson(data);

            Assert.AreEqual("{\"cmd\":\"test\"}", json,
                "TC-MSGPACK-C#-01: fixmap with fixstr values must decode to valid JSON");
        }

        // ── TC-MSGPACK-C#-02 ─────────────────────────────────────────────────

        [Test]
        public void Decode_Float32Value_WithinPrecision()
        {
            // {"v": 0.5f}  (0.5 as IEEE-754 float32 big-endian = 3F 00 00 00)
            // 81  a1 76  ca 3f 00 00 00
            byte[] data =
            {
                0x81,                               // fixmap, count=1
                0xa1, 0x76,                        // fixstr(1) "v"
                0xca, 0x3f, 0x00, 0x00, 0x00,     // float32 0.5
            };

            string json = MsgPackDecoder.ToJson(data);

            // Extract numeric part after "v":
            // JSON looks like {"v":0.5}
            Assert.IsTrue(json.Contains("\"v\":"), $"TC-MSGPACK-C#-02: missing key 'v' in {json}");
            int colon = json.IndexOf("\"v\":") + 4;
            int end   = json.IndexOf('}', colon);
            float val = float.Parse(json.Substring(colon, end - colon),
                System.Globalization.CultureInfo.InvariantCulture);
            Assert.AreEqual(0.5f, val, 0.001f,
                "TC-MSGPACK-C#-02: float32 0.5 must decode to 0.5 ± 0.001");
        }

        // ── TC-MSGPACK-C#-03 ─────────────────────────────────────────────────

        [Test]
        public void Decode_NestedMap_ProducesNestedJson()
        {
            // {"a":{"b":1}}
            // 81  a1 61  81  a1 62  01
            byte[] data =
            {
                0x81,                   // fixmap, count=1
                0xa1, 0x61,            // fixstr(1) "a"
                0x81,                  // fixmap, count=1
                0xa1, 0x62,            // fixstr(1) "b"
                0x01,                  // positive fixint = 1
            };

            string json = MsgPackDecoder.ToJson(data);

            Assert.IsTrue(json.Contains("\"a\":"), $"TC-MSGPACK-C#-03: missing key 'a' in {json}");
            Assert.IsTrue(json.Contains("\"b\":1"), $"TC-MSGPACK-C#-03: missing nested b:1 in {json}");
        }

        // ── TC-MSGPACK-C#-04 ─────────────────────────────────────────────────

        [Test]
        public void Decode_BoolAndNull_ProducesJsonLiterals()
        {
            // {"ok":true,"x":null}
            // 82  a2 6f 6b  c3  a1 78  c0
            byte[] data =
            {
                0x82,                           // fixmap, count=2
                0xa2, 0x6f, 0x6b,              // fixstr(2) "ok"
                0xc3,                          // true
                0xa1, 0x78,                    // fixstr(1) "x"
                0xc0,                          // nil → null
            };

            string json = MsgPackDecoder.ToJson(data);

            Assert.IsTrue(json.Contains("\"ok\":true"),   $"TC-MSGPACK-C#-04: expected true in {json}");
            Assert.IsTrue(json.Contains("\"x\":null"),    $"TC-MSGPACK-C#-04: expected null in {json}");
        }
    }
}

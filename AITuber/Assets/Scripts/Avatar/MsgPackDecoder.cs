// MsgPackDecoder.cs
// Minimal MessagePack → JSON string decoder for AITuber WS messages.
// FR-PERF-01 / Issue #61: Binary WebSocket transport.
//
// Supported types: fixmap, map16/32, fixstr, str8/16/32,
//   positive/negative fixint, uint8/16/32/64, int8/16/32/64,
//   float32, float64, bool, nil, fixarray, array16/32.
// No external dependencies — self-contained, no MessagePack-CSharp required.

using System;
using System.Globalization;
using System.Text;

namespace AITuber.Avatar
{
    /// <summary>
    /// Converts a MessagePack binary buffer to a JSON string so that the existing
    /// <see cref="AvatarMessageParser"/> pipeline can process binary WS frames.
    /// </summary>
    public static class MsgPackDecoder
    {
        /// <summary>Decode <paramref name="data"/> from MessagePack and return JSON.</summary>
        /// <exception cref="FormatException">Thrown on malformed input.</exception>
        public static string ToJson(byte[] data)
        {
            int pos = 0;
            var sb = new StringBuilder(data.Length * 2);
            DecodeValue(data, ref pos, sb);
            return sb.ToString();
        }

        // ── Core decoder ─────────────────────────────────────────────

        private static void DecodeValue(byte[] d, ref int pos, StringBuilder sb)
        {
            byte b = d[pos++];

            // Positive fixint 0x00–0x7f
            if (b <= 0x7f) { sb.Append(b); return; }

            // Negative fixint 0xe0–0xff
            if (b >= 0xe0) { sb.Append((sbyte)b); return; }

            // fixmap 0x80–0x8f
            if ((b & 0xf0) == 0x80) { DecodeMap(d, ref pos, sb, b & 0x0f); return; }

            // fixarray 0x90–0x9f
            if ((b & 0xf0) == 0x90) { DecodeArray(d, ref pos, sb, b & 0x0f); return; }

            // fixstr 0xa0–0xbf
            if ((b & 0xe0) == 0xa0) { DecodeStr(d, ref pos, sb, b & 0x1f); return; }

            switch (b)
            {
                case 0xc0: sb.Append("null"); break;
                case 0xc2: sb.Append("false"); break;
                case 0xc3: sb.Append("true"); break;

                case 0xca: // float32
                {
                    var buf = new byte[4];
                    Array.Copy(d, pos, buf, 0, 4);
                    if (BitConverter.IsLittleEndian) Array.Reverse(buf);
                    float v = BitConverter.ToSingle(buf, 0);
                    sb.Append(v.ToString("G9", CultureInfo.InvariantCulture));
                    pos += 4;
                    break;
                }
                case 0xcb: // float64
                {
                    var buf = new byte[8];
                    Array.Copy(d, pos, buf, 0, 8);
                    if (BitConverter.IsLittleEndian) Array.Reverse(buf);
                    double v = BitConverter.ToDouble(buf, 0);
                    sb.Append(v.ToString("G17", CultureInfo.InvariantCulture));
                    pos += 8;
                    break;
                }

                case 0xcc: sb.Append(d[pos++]); break;                                             // uint8
                case 0xcd: sb.Append((d[pos] << 8) | d[pos + 1]); pos += 2; break;                // uint16
                case 0xce:                                                                          // uint32
                {
                    uint v = ((uint)d[pos] << 24) | ((uint)d[pos + 1] << 16)
                           | ((uint)d[pos + 2] << 8) | d[pos + 3];
                    sb.Append(v); pos += 4; break;
                }
                case 0xcf: sb.Append(ReadU64(d, pos)); pos += 8; break;                            // uint64

                case 0xd0: sb.Append((sbyte)d[pos++]); break;                                      // int8
                case 0xd1: sb.Append((short)((d[pos] << 8) | d[pos + 1])); pos += 2; break;       // int16
                case 0xd2:                                                                          // int32
                {
                    int v = (int)(((uint)d[pos] << 24) | ((uint)d[pos + 1] << 16)
                                | ((uint)d[pos + 2] << 8) | d[pos + 3]);
                    sb.Append(v); pos += 4; break;
                }
                case 0xd3: sb.Append((long)ReadU64(d, pos)); pos += 8; break;                      // int64

                case 0xd9: { int n = d[pos++]; DecodeStr(d, ref pos, sb, n); break; }              // str8
                case 0xda: { int n = (d[pos] << 8) | d[pos + 1]; pos += 2; DecodeStr(d, ref pos, sb, n); break; } // str16
                case 0xdb:                                                                          // str32
                {
                    int n = (int)(((uint)d[pos] << 24) | ((uint)d[pos + 1] << 16)
                                | ((uint)d[pos + 2] << 8) | d[pos + 3]);
                    pos += 4; DecodeStr(d, ref pos, sb, n); break;
                }

                case 0xdc: { int n = (d[pos] << 8) | d[pos + 1]; pos += 2; DecodeArray(d, ref pos, sb, n); break; } // array16
                case 0xdd:                                                                          // array32
                {
                    int n = (int)(((uint)d[pos] << 24) | ((uint)d[pos + 1] << 16)
                                | ((uint)d[pos + 2] << 8) | d[pos + 3]);
                    pos += 4; DecodeArray(d, ref pos, sb, n); break;
                }

                case 0xde: { int n = (d[pos] << 8) | d[pos + 1]; pos += 2; DecodeMap(d, ref pos, sb, n); break; }  // map16
                case 0xdf:                                                                          // map32
                {
                    int n = (int)(((uint)d[pos] << 24) | ((uint)d[pos + 1] << 16)
                                | ((uint)d[pos + 2] << 8) | d[pos + 3]);
                    pos += 4; DecodeMap(d, ref pos, sb, n); break;
                }

                default:
                    throw new FormatException(
                        $"Unsupported MessagePack byte 0x{b:x2} at position {pos - 1}");
            }
        }

        // ── Helpers ──────────────────────────────────────────────────

        private static void DecodeStr(byte[] d, ref int pos, StringBuilder sb, int len)
        {
            sb.Append('"');
            string s = Encoding.UTF8.GetString(d, pos, len);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"':  sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n");  break;
                    case '\r': sb.Append("\\r");  break;
                    case '\t': sb.Append("\\t");  break;
                    default:
                        if (c < 0x20) sb.AppendFormat("\\u{0:x4}", (int)c);
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
            pos += len;
        }

        private static void DecodeMap(byte[] d, ref int pos, StringBuilder sb, int count)
        {
            sb.Append('{');
            for (int i = 0; i < count; i++)
            {
                if (i > 0) sb.Append(',');
                DecodeValue(d, ref pos, sb); // key
                sb.Append(':');
                DecodeValue(d, ref pos, sb); // value
            }
            sb.Append('}');
        }

        private static void DecodeArray(byte[] d, ref int pos, StringBuilder sb, int count)
        {
            sb.Append('[');
            for (int i = 0; i < count; i++)
            {
                if (i > 0) sb.Append(',');
                DecodeValue(d, ref pos, sb);
            }
            sb.Append(']');
        }

        private static ulong ReadU64(byte[] d, int pos) =>
            ((ulong)d[pos]     << 56) | ((ulong)d[pos + 1] << 48) |
            ((ulong)d[pos + 2] << 40) | ((ulong)d[pos + 3] << 32) |
            ((ulong)d[pos + 4] << 24) | ((ulong)d[pos + 5] << 16) |
            ((ulong)d[pos + 6] <<  8) |  (ulong)d[pos + 7];
    }
}

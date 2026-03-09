// DebugMotionUI.cs
// 再生中にジェスチャー・エモーションを手動トリガーするデバッグUI。
// AvatarController は FindAnyObjectByType で自動解決 → Inspector配線不要。
//
// 操作:
//   F2 キー : パネルの表示/非表示切替
//   ウィンドウはドラッグで位置を移動可能
//
// ★ B方式: avatar_update JSON を HandleMessage(string json) に流すことで
//   実際の WebSocket 受信と完全に同じコードパスを通る。
//   emotion + gesture + look_target が連動して動作する。
//
// Attach: 任意のGameObject（例: DebugTools）にアタッチするか、
//         Any Sceneに空オブジェクトを作成してAddComponentするだけでOK。
//
// SRS refs: (デバッグ専用 / SRS対象外)

using System;
using System.Net.Http;
using System.Text;
using UnityEngine;
using AITuber.Avatar;
using AITuber.Behavior;

namespace AITuber
{
    public class DebugMotionUI : MonoBehaviour
    {
        [Header("Toggle Key")]
        [SerializeField] private KeyCode _toggleKey = KeyCode.F2;

        [Header("Window")]
        [SerializeField] private bool _showOnStart = true;
        [SerializeField] private float _windowWidth  = 260f;
        [SerializeField] private float _windowHeight = 720f;

        // ── private state ──────────────────────────────────────────────
        private bool _visible;
        private Rect _windowRect;
        private Vector2 _gestureScroll;
        private AvatarController _avatar;
        private GUIStyle _headerStyle;
        private GUIStyle _buttonStyle;
        private GUIStyle _activeButtonStyle;
        private string _lastAction = "";

        // A2F lip sync test
        private Audio2FaceLipSync _a2fLipSync;
        private string _a2fStatus = "--";
        private AudioSource _a2fAudioSource;

        // TTS → A2F テスト
        private string _a2fTtsText   = "こんにちは、ゆいあです";
        private string _a2fVvUrl     = "http://localhost:50021";
        private int    _a2fSpeakerId = 47;
        private bool   _a2fTtsRunning;

        // 現在選択中の emotion / look_target（gesture ボタンに連動する）
        private string _selectedEmotion    = "neutral";
        private string _selectedLookTarget = "camera";

        // ── Gesture list ───────────────────────────────────────────────
        // hasClip=false はアニメーションクリップ未割り当て（Idle_Breathing で代替中 or 空）
        private static readonly (string label, string gesture, bool hasClip)[] k_Gestures =
        {
            // 基本（clip あり）
            ("うなずく",         "nod",            true),
            ("首ふり",           "shake",           true),
            ("手を振る",         "wave",            true),
            ("チアー",           "cheer",           true),
            ("肩をすくめる",     "shrug",           true),
            ("フェイスパーム",   "facepalm",        true),
            // 感情・リアクション
            ("照れる",           "shy",             true),
            ("笑う",             "laugh",           true),
            ("驚く",             "surprised",       true),
            ("落ち込む",         "rejected",        true),
            ("ため息",           "sigh",            true),
            ("感謝",             "thankful",        true),
            // 悲しみ
            ("悲しいアイドル",   "sad_idle",        true),
            ("悲しいキック",     "sad_kick",        true),
            // 思考
            ("考える",           "thinking",        true),
            // アイドル
            ("アイドルAlt",      "idle_alt",        true),
            // 座り系（clip あり）
            ("座る",             "sit_down",        true),
            ("座りアイドル",     "sit_idle",        true),
            ("座って笑う",       "sit_laugh",       true),
            ("座って拍手",       "sit_clap",        true),
            ("座って疑問",       "sit_disbelief",   true),
            ("座ってキック",     "sit_kick",        true),
            // ── clip 未割り当て（グレーアウト表示）──────────────────
            ("お辞儀",           "bow",             false),
            ("拍手",             "clap",            false),
            ("サムズアップ",     "thumbs_up",       false),
            ("前を指す",         "point_forward",   false),
            ("スピン",           "spin",            false),
            ("座って指す",       "sit_point",       false),
            ("座って読む",       "sit_read",        false),
            ("座って食べる",     "sit_eat",         false),
            ("座って書く",       "sit_write",       false),
            ("歩く",             "walk",            true),
            ("歩き止まる",       "walk_stop",       true),
            ("歩き→止まり",     "walk_stop_start", true),
            ("寝る",             "sleep_idle",      false),
            ("ストレッチ",       "stretch",         false),
        };

        // ── Behavior list ──────────────────────────────────────────────
        private static readonly (string label, string behavior)[] k_Behaviors =
        {
            ("就寝",       "go_sleep"),
            ("起床",       "go_wake"),
            ("食事",       "go_eat"),
            ("読書",       "go_read"),
            ("配信",       "go_stream"),
            ("散歩",       "go_walk"),
            ("ストレッチ", "go_stretch"),
        };

        // ── Emotion list ───────────────────────────────────────────────
        private static readonly (string label, string emotion)[] k_Emotions =
        {
            ("ニュートラル", "neutral"),
            ("喜び",         "happy"),
            ("悲しみ",       "sad"),
            ("怒り",         "angry"),
            ("驚き",         "surprise"),
            ("考え中",       "thinking"),
        };

        // ── LookTarget list ─────────────────────────────────────────────
        private static readonly (string label, string target)[] k_LookTargets =
        {
            ("カメラ",   "camera"),
            ("左",       "viewer_left"),
            ("右",       "viewer_right"),
            ("下",       "viewer_down"),
        };

        // ──────────────────────────────────────────────────────────────

        private void Start()
        {
            _visible     = _showOnStart;
            _windowRect  = new Rect(10f, 10f, _windowWidth, _windowHeight);
        }

        private void Update()
        {
            if (Input.GetKeyDown(_toggleKey))
                _visible = !_visible;

            // AvatarController を遅延解決（Start時点でまだ存在しない場合に対応）
            if (_avatar == null)
                _avatar = FindAnyObjectByType<AvatarController>();
            if (_a2fLipSync == null)
                _a2fLipSync = FindAnyObjectByType<Audio2FaceLipSync>();

            // A2F ステータス更新
            if (_a2fLipSync != null)
            {
                _a2fStatus = _a2fLipSync.IsReady
                    ? (_a2fLipSync.IsSpeaking ? "▶ Speaking" : "✔ Ready")
                    : "✖ Not Ready";
            }
            else
            {
                _a2fStatus = "(component not found)";
            }
        }

        private void OnGUI()
        {
            if (!_visible) return;

            EnsureStyles();

            _windowRect = GUI.Window(7711, _windowRect, DrawWindow, "🎭 Debug Motion UI  [F2]");
        }

        private void DrawWindow(int id)
        {
            GUILayout.Space(4f);

            // ── Avatar 状態 ──────────────────────────────────────
            if (_avatar == null)
            {
                GUILayout.Label("⚠ AvatarController not found", _headerStyle);
                GUI.DragWindow();
                return;
            }

            // ── Emotion ──────────────────────────────────────────
            GUILayout.Label("■ Emotion", _headerStyle);
            GUILayout.BeginHorizontal();
            foreach (var (lbl, emo) in k_Emotions)
            {
                var style = emo == _selectedEmotion ? _activeButtonStyle : _buttonStyle;
                if (GUILayout.Button(lbl, style, GUILayout.Height(28f)))
                {
                    _selectedEmotion = emo;
                    // emotion 変更を avatar_update で反映（gesture は none でニュートラル）
                    SendUpdate(_selectedEmotion, "none", _selectedLookTarget);
                    _lastAction = $"emotion: {emo}";
                }
            }
            GUILayout.EndHorizontal();

            GUILayout.Space(4f);

            // ── LookTarget ──────────────────────────────────────
            GUILayout.Label("■ 視線", _headerStyle);
            GUILayout.BeginHorizontal();
            foreach (var (lbl, tgt) in k_LookTargets)
            {
                var style = tgt == _selectedLookTarget ? _activeButtonStyle : _buttonStyle;
                if (GUILayout.Button(lbl, style, GUILayout.Height(24f)))
                {
                    _selectedLookTarget = tgt;
                    SendUpdate(_selectedEmotion, "none", _selectedLookTarget);
                    _lastAction = $"look: {tgt}";
                }
            }
            GUILayout.EndHorizontal();

            GUILayout.Space(6f);

            // ── Gesture ──────────────────────────────────────────
            GUILayout.Label("■ Gesture", _headerStyle);

            float bh  = 30f;
            float bw  = (_windowWidth - 24f) / 2f;
            const float listH = 220f; // ジェスチャーScrollViewの固定高さ

            _gestureScroll = GUILayout.BeginScrollView(
                _gestureScroll,
                GUILayout.Height(listH));

            int col = 0;
            foreach (var (lbl, ges, hasClip) in k_Gestures)
            {
                if (col % 2 == 0) GUILayout.BeginHorizontal();

                GUI.enabled = hasClip;
                string btnLabel = hasClip ? lbl : $"{lbl} (未)";
                if (GUILayout.Button(btnLabel, _buttonStyle, GUILayout.Width(bw), GUILayout.Height(bh)))
                {
                    // dedup リセット: gesture="none" を先に送ってから目的ジェスチャーを発火
                    // → 実際の WS と同じ HandleMessage コードパスを通る
                    SendUpdate(_selectedEmotion, "none",  _selectedLookTarget);
                    SendUpdate(_selectedEmotion, ges,     _selectedLookTarget);
                    _lastAction = $"gesture: {ges}  emotion: {_selectedEmotion}";
                }
                GUI.enabled = true;

                if (col % 2 == 1) GUILayout.EndHorizontal();
                col++;
            }
            // 奇数個の場合に最後の行を閉じる
            if (col % 2 == 1)
            {
                GUILayout.FlexibleSpace();
                GUILayout.EndHorizontal();
            }

            GUILayout.EndScrollView();

            GUILayout.Space(4f);

            // ── Behavior Sequence ───────────────────────────────
            var runner = BehaviorSequenceRunner.Instance;
            string runLabel = runner != null && runner.IsBusy
                ? $"▶ {runner.RunningBehavior}"
                : "■ 停止中";
            GUILayout.Label($"■ Behavior  [{runLabel}]", _headerStyle);

            int bCol = 0;
            foreach (var (blbl, bname) in k_Behaviors)
            {
                if (bCol % 3 == 0) GUILayout.BeginHorizontal();
                if (GUILayout.Button(blbl, _buttonStyle, GUILayout.Height(26f)))
                {
                    SendBehavior(bname);
                    _lastAction = $"behavior: {bname}";
                }
                if (bCol % 3 == 2) GUILayout.EndHorizontal();
                bCol++;
            }
            if (bCol % 3 != 0)
            {
                GUILayout.FlexibleSpace();
                GUILayout.EndHorizontal();
            }
            if (runner != null && runner.IsBusy)
            {
                if (GUILayout.Button("⏹ STOP", _activeButtonStyle, GUILayout.Height(24f)))
                {
                    runner.StopBehavior();
                    _lastAction = "behavior: STOP";
                }
            }

            GUILayout.Space(4f);

            // ── A2F TTS テスト ───────────────────────────────────
            GUILayout.Label($"■ A2F TTS テスト  [{_a2fStatus}]", _headerStyle);
            _a2fTtsText = GUILayout.TextField(_a2fTtsText);
            GUILayout.BeginHorizontal();
            bool canA2FTts = _a2fLipSync != null && _a2fLipSync.IsReady && !_a2fTtsRunning;
            GUI.enabled = canA2FTts;
            if (GUILayout.Button(_a2fTtsRunning ? "合成中..." : "▶ TTS→A2F", _buttonStyle, GUILayout.Height(26f)))
            {
                SendA2FTTS(_a2fTtsText);
                _lastAction = $"a2f: TTS \"{_a2fTtsText}\"";
            }
            GUI.enabled = true;
            if (GUILayout.Button("サイン波", _buttonStyle, GUILayout.Height(26f)))
            {
                SendA2FSineWave(4.0f, 220f);
                _lastAction = "a2f: sine 220Hz 4.0s";
            }
            if (GUILayout.Button("停止", _buttonStyle, GUILayout.Height(26f)))
            {
                if (_a2fLipSync != null) _a2fLipSync.StopSpeaking();
                _lastAction = "a2f: stop";
            }
            GUILayout.EndHorizontal();

            GUILayout.Space(4f);

            // ── 直前のアクション表示 ─────────────────────────────
            if (!string.IsNullOrEmpty(_lastAction))
                GUILayout.Label($"▶ {_lastAction}", _buttonStyle);

            GUI.DragWindow();
        }

        /// <summary>
        /// avatar_update JSON を構築し HandleMessage(string) に渡す。
        /// 実際の WebSocket 受信と完全に同じコードパスを通る（B方式）。
        /// </summary>
        private void SendUpdate(string emotion, string gesture, string lookTarget)
        {
            if (_avatar == null) return;
            // AvatarMessageParser が期待するフォーマット
            string json = $"{{\"id\":\"dbg\",\"ts\":\"2026-01-01T00:00:00Z\"," +
                          $"\"cmd\":\"avatar_update\"," +
                          $"\"params\":{{\"emotion\":\"{emotion}\"," +
                          $"\"gesture\":\"{gesture}\"," +
                          $"\"look_target\":\"{lookTarget}\"," +
                          $"\"mouth_open\":0}}}}";
            _avatar.HandleMessage(json);
        }

        /// <summary>
        /// behavior_start JSON を構築し HandleMessage(string) に渡す。
        /// BehaviorSequenceRunner 経由でシーケンスを実行する。
        /// </summary>
        private void SendBehavior(string behaviorName)
        {
            if (_avatar == null) return;
            string json = $"{{\"id\":\"dbg\",\"ts\":\"2026-01-01T00:00:00Z\"," +
                          $"\"cmd\":\"behavior_start\"," +
                          $"\"params\":{{\"behavior\":\"{behaviorName}\"}}}}";
            _avatar.HandleMessage(json);
        }

        /// <summary>
        /// VOICEVOX でテキストを合成し float[] PCM を A2F に渡す。
        /// 24kHz WAV を 16kHz にリサンプルして <see cref="Audio2FaceLipSync.ProcessAudio"/> を呼ぶ。
        /// </summary>
        private async void SendA2FTTS(string text)
        {
            if (string.IsNullOrWhiteSpace(text) || _a2fLipSync == null || !_a2fLipSync.IsReady) return;
            _a2fTtsRunning = true;
            _a2fStatus     = "⏳ 合成中...";
            try
            {
                byte[] wav = null;
                var url = _a2fVvUrl;
                var spk = _a2fSpeakerId;
                await System.Threading.Tasks.Task.Run(async () =>
                {
                    using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                    var qResp = await client.PostAsync(
                        $"{url}/audio_query?speaker={spk}&text={Uri.EscapeDataString(text)}", null);
                    if (!qResp.IsSuccessStatusCode)
                        throw new Exception($"audio_query failed: {qResp.StatusCode}");
                    var qJson = await qResp.Content.ReadAsStringAsync();
                    var sResp = await client.PostAsync(
                        $"{url}/synthesis?speaker={spk}",
                        new StringContent(qJson, Encoding.UTF8, "application/json"));
                    if (!sResp.IsSuccessStatusCode)
                        throw new Exception($"synthesis failed: {sResp.StatusCode}");
                    wav = await sResp.Content.ReadAsByteArrayAsync();
                });

                float[] pcm24k = WavToFloat(wav);
                float[] pcm16k = ResampleLinear(pcm24k, 24000, 16000);

                // AudioSource で音声を再生（A2F はリップシンクのみでサウンドを持たないため）
                var clip = AudioClip.Create("tts_a2f", pcm24k.Length, 1, 24000, false);
                clip.SetData(pcm24k, 0);
                if (_a2fAudioSource == null)
                {
                    _a2fAudioSource = GetComponent<AudioSource>();
                    if (_a2fAudioSource == null)
                        _a2fAudioSource = gameObject.AddComponent<AudioSource>();
                    _a2fAudioSource.spatialBlend = 0f;  // 2D
                }
                _a2fAudioSource.clip = clip;
                _a2fAudioSource.Play();

                _a2fLipSync.ProcessAudio(pcm16k);
                _a2fStatus = $"✔ Ready  ({pcm16k.Length / 16000f:F1}s)";
            }
            catch (Exception ex)
            {
                _a2fStatus = $"✖ {ex.Message}";
                Debug.LogError($"[DebugMotionUI] A2F TTS: {ex}");
            }
            finally
            {
                _a2fTtsRunning = false;
            }
        }

        private static float[] WavToFloat(byte[] wav)
        {
            int pos = 12;
            while (pos < wav.Length - 8)
            {
                string id = Encoding.ASCII.GetString(wav, pos, 4);
                int    sz = BitConverter.ToInt32(wav, pos + 4);
                pos += 8;
                if (id == "data") break;
                pos += sz;
            }
            int count   = (wav.Length - pos) / 2;
            var samples = new float[count];
            for (int i = 0; i < count; i++)
            {
                short s = BitConverter.ToInt16(wav, pos + i * 2);
                samples[i] = s / 32768f;
            }
            return samples;
        }

        private static float[] ResampleLinear(float[] src, int inRate, int outRate)
        {
            if (inRate == outRate) return src;
            int   outLen = (int)((long)src.Length * outRate / inRate);
            var   dst    = new float[outLen];
            float step   = (float)inRate / outRate;
            for (int i = 0; i < outLen; i++)
            {
                float pos  = i * step;
                int   idx  = (int)pos;
                float frac = pos - idx;
                float a = idx     < src.Length ? src[idx]     : 0f;
                float b = idx + 1 < src.Length ? src[idx + 1] : 0f;
                dst[i] = a + frac * (b - a);
            }
            return dst;
        }

        /// <summary>
        /// サイン波 PCM を生成して Audio2FaceLipSync に流すデバッグ用メソッド。
        /// Unity Microphone の代わりに、A2F プラグインが動いているかを確認できる。
        /// </summary>
        private void SendA2FSineWave(float durationSec, float freqHz)
        {
            if (_a2fLipSync == null || !_a2fLipSync.IsReady)
            {
                _a2fStatus = "\u2716 Not Ready";
                return;
            }
            int sr = 16000;
            int n  = Mathf.RoundToInt(durationSec * sr);
            float[] pcm = new float[n];
            for (int i = 0; i < n; i++)
                pcm[i] = Mathf.Sin(2f * Mathf.PI * freqHz * i / sr) * 0.8f;
            _a2fLipSync.ProcessAudio(pcm);
        }

        // ── Style 初期化（OnGUI 初回のみ）────────────────────────

        private void EnsureStyles()
        {
            // domain reload 後にGUIStyleがnullになるため、毎回nullチェックで再初期化
            if (_buttonStyle != null) return;

            _headerStyle = new GUIStyle(GUI.skin.label)
            {
                fontStyle = FontStyle.Bold,
                fontSize  = 13,
                normal    = { textColor = new Color(0.9f, 0.9f, 0.4f) },
            };

            _buttonStyle = new GUIStyle(GUI.skin.button)
            {
                fontSize  = 11,
                wordWrap  = true,
                alignment = TextAnchor.MiddleCenter,
            };

            // 選択中ボタン（黄色テキストで強調）
            _activeButtonStyle = new GUIStyle(_buttonStyle)
            {
                fontStyle = FontStyle.Bold,
                normal    = { textColor = new Color(0.2f, 1f, 0.2f) },
                hover     = { textColor = new Color(0.2f, 1f, 0.2f) },
            };
        }
    }
}

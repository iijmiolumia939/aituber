// AvatarDebugWindow.cs
// Editor ウィンドウ: WebSocket なしで AvatarController に直接コマンドを送りテストする。
// Unity メニュー → AITuber / Avatar Debug Window

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;
using AITuber.Avatar;

namespace AITuber.Editor
{
    public class AvatarDebugWindow : EditorWindow
    {
        // ── Gesture / Emotion / LookTarget テーブル ────────────────────
        private static readonly string[] Gestures =
        {
            "none",
            // 既存
            "nod", "shake", "wave", "cheer", "shrug", "facepalm",
            // Mixamo 感情
            "shy", "laugh", "surprised", "rejected", "sigh", "thankful",
            // 悲しみ
            "sad_idle", "sad_kick",
            // 思考
            "thinking",
            // 代替アイドル
            "idle_alt",
            // 座り
            "sit_down", "sit_idle", "sit_laugh", "sit_clap",
            "sit_point", "sit_disbelief", "sit_kick",
        };

        private static readonly string[] Emotions =
            { "neutral", "happy", "thinking", "surprised", "sad", "angry", "panic" };

        private static readonly string[] LookTargets =
            { "camera", "chat", "down", "random" };

        private static readonly string[] Vowels = { "sil", "a", "i", "u", "e", "o", "m", "fv" };

        // ── State ──────────────────────────────────────────────────────
        private Vector2 _scroll;
        private string  _status = "Ready.";
        private Color   _statusColor = Color.gray;

        // Gesture grid
        private int _gestureColumns = 4;

        // Emotion
        private int _selectedEmotion = 0;

        // LookAt
        private int _selectedLook = 0;

        // Lip sync シミュレーション
        private bool   _lipSyncRunning;
        private double _lipSyncStartTime;
        private int    _lipSyncStep;
        private static readonly (string v, int dt)[] LipSyncDemo =
        {
            ("a",   0), ("i", 150), ("u", 280), ("e", 400),
            ("o", 550), ("a", 700), ("m", 850), ("sil", 1000),
        };

        // TTS テスト
        private string _ttsText      = "あいうえお、こんにちは";
        private string _voicevoxUrl  = "http://localhost:50021";
        private int    _speakerId    = 47;
        private bool   _ttsRunning   = false;
        private bool   _useA2f       = true;
        private static readonly Dictionary<string, string> VowelToText = new Dictionary<string, string>
        {
            ["a"] = "あ", ["i"] = "い", ["u"] = "う",
            ["e"] = "え", ["o"] = "お", ["m"] = "ん",
            ["fv"] = "ふ", ["sil"] = "",
        };

        // ── Menu ───────────────────────────────────────────────────────
        [MenuItem("AITuber/Avatar Debug Window")]
        public static void ShowWindow()
            => GetWindow<AvatarDebugWindow>("Avatar Debug").Show();

        // ── GUI ────────────────────────────────────────────────────────
        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            DrawStatus();
            DrawA2FSection();
            DrawGestureSection();
            DrawEmotionSection();
            DrawLookTargetSection();
            DrawEyeQualitySection();
            DrawTTSSection();
            DrawLipSyncSection();
            DrawResetSection();

            EditorGUILayout.EndScrollView();

            // リップシンクアニメーション中はリドロー
            if (_lipSyncRunning)
            {
                TickLipSync();
                Repaint();
            }
        }

        // ── Status bar ─────────────────────────────────────────────────
        private void DrawStatus()
        {
            EditorGUILayout.Space(4);
            var style = new GUIStyle(EditorStyles.helpBox);
            style.fontSize = 11;
            using (new EditorGUILayout.HorizontalScope(style))
            {
                var old = GUI.color;
                GUI.color = _statusColor;
                EditorGUILayout.LabelField(_status, GUILayout.ExpandWidth(true));
                GUI.color = old;
            }
            EditorGUILayout.Space(4);
        }

        // ── Gestures ───────────────────────────────────────────────────
        private void DrawGestureSection()
        {
            EditorGUILayout.LabelField("Gesture", EditorStyles.boldLabel);
            int col = 0;
            EditorGUILayout.BeginHorizontal();
            foreach (var g in Gestures)
            {
                if (GUILayout.Button(g, GUILayout.Width(130)))
                    SendGesture(g);
                col++;
                if (col >= _gestureColumns)
                {
                    EditorGUILayout.EndHorizontal();
                    EditorGUILayout.BeginHorizontal();
                    col = 0;
                }
            }
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.Space(6);
        }

        // ── Emotions ───────────────────────────────────────────────────
        private void DrawEmotionSection()
        {
            EditorGUILayout.LabelField("Emotion", EditorStyles.boldLabel);
            EditorGUILayout.BeginHorizontal();
            foreach (var e in Emotions)
            {
                if (GUILayout.Button(e))
                    SendEmotion(e);
            }
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.Space(6);
        }

        // ── LookAt ─────────────────────────────────────────────────────
        private void DrawLookTargetSection()
        {
            EditorGUILayout.LabelField("Look Target", EditorStyles.boldLabel);
            EditorGUILayout.BeginHorizontal();
            foreach (var t in LookTargets)
            {
                if (GUILayout.Button(t))
                    SendLookTarget(t);
            }
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.Space(6);
        }

        // ── Eye / 実在感 テスト ────────────────────────────────────────
        private bool _commentScanActive;

        private void DrawEyeQualitySection()
        {
            EditorGUILayout.LabelField("Eye / 実在感 テスト", EditorStyles.boldLabel);

            // (A) Saccade
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("(A) Saccade",     GUILayout.Width(110));
                var oldColor = GUI.color;
                GUI.color = new Color(0.5f, 1f, 0.5f);
                EditorGUILayout.LabelField("常時動作中", EditorStyles.miniLabel);
                GUI.color = oldColor;
            }

            // (C) Breathing
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("(C) 呼吸",        GUILayout.Width(110));
                var oldColor = GUI.color;
                GUI.color = new Color(0.5f, 1f, 0.5f);
                EditorGUILayout.LabelField("常時動作中 (Chest bone)", EditorStyles.miniLabel);
                GUI.color = oldColor;
            }

            EditorGUILayout.Space(4);

            // (B) Emotion-linked blink
            EditorGUILayout.LabelField("(B) 感情連動まばたき", EditorStyles.miniBoldLabel);
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("surprised\n(5s 停止)",  GUILayout.Width(90), GUILayout.Height(36)))
                    SendEmotion("surprised");
                if (GUILayout.Button("happy\n(速)",           GUILayout.Width(90), GUILayout.Height(36)))
                    SendEmotion("happy");
                if (GUILayout.Button("sad\n(重い瞼)",         GUILayout.Width(90), GUILayout.Height(36)))
                    SendEmotion("sad");
                if (GUILayout.Button("neutral\n(リセット)",   GUILayout.Width(90), GUILayout.Height(36)))
                    SendEmotion("neutral");
            }

            EditorGUILayout.Space(4);

            // Comment scan gaze
            EditorGUILayout.LabelField("コメント視線スキャン", EditorStyles.miniBoldLabel);

            // Show current anchor info for diagnosis
            {
                var ctrl = (Application.isPlaying ? FindController() : null)
                           ?? UnityEngine.Object.FindFirstObjectByType<AvatarController>();
                if (ctrl != null)
                {
                    var anchorField = typeof(AvatarController).GetField("_commentAreaAnchor",
                        System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    var chatField   = typeof(AvatarController).GetField("_lookAtChat",
                        System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    var anchor = anchorField?.GetValue(ctrl) as Transform;
                    var chat   = chatField?.GetValue(ctrl) as Transform;

                    string anchorInfo;
                    Color  anchorColor;
                    if (anchor != null)
                    {
                        anchorInfo  = $"✓ CommentAreaAnchor={anchor.name}  pos={anchor.position:F2}";
                        anchorColor = Color.green;
                    }
                    else if (chat != null)
                    {
                        anchorInfo  = $"⚠ Anchor未設定 → fallback _lookAtChat={chat.name}\n  AITuber/Setup Comment Area で作成してください";
                        anchorColor = Color.yellow;
                    }
                    else
                    {
                        anchorInfo  = "❌ CommentAreaAnchorも_lookAtChatも未設定";
                        anchorColor = Color.red;
                    }
                    var infoStyle = new GUIStyle(EditorStyles.miniLabel)
                        { wordWrap = true, normal = { textColor = anchorColor } };
                    EditorGUILayout.LabelField(anchorInfo, infoStyle);

                    if (anchor == null && GUILayout.Button("► AITuber/Setup Comment Area を実行", GUILayout.Height(22)))
                        EditorApplication.ExecuteMenuItem("AITuber/Setup Comment Area");
                }
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                GUI.enabled = Application.isPlaying && !_commentScanActive;
                if (GUILayout.Button("▶ comment_read_start", GUILayout.Width(180)))
                {
                    SendAvatarEvent("comment_read_start", 1.0f);
                    _commentScanActive = true;
                    SetStatus("👁 Comment scan started", Color.cyan);
                }
                GUI.enabled = Application.isPlaying && _commentScanActive;
                if (GUILayout.Button("■ comment_read_end", GUILayout.Width(160)))
                {
                    SendAvatarEvent("comment_read_end", 0.0f);
                    _commentScanActive = false;
                    SetStatus("👁 Comment scan stopped", Color.white);
                }
                GUI.enabled = true;
            }

            if (!Application.isPlaying)
                EditorGUILayout.HelpBox("Play Mode 中のみ動作します。", MessageType.Info);

            EditorGUILayout.Space(6);
        }

        // ── A2F Neural Lip Sync テスト ─────────────────────────────
        private void DrawA2FSection()
        {
            var a2f = Application.isPlaying
                ? UnityEngine.Object.FindFirstObjectByType<Audio2FaceLipSync>()
                : null;

            string statusStr;
            Color  statusColor;
            if (!Application.isPlaying)  { statusStr = "Play Mode で起動してください";             statusColor = Color.gray; }
            else if (a2f == null)        { statusStr = "⚠ Audio2FaceLipSync コンポーネント未設定"; statusColor = Color.red; }
            else if (!a2f.IsReady)       { statusStr = "⏳ 初期化中...";                           statusColor = Color.yellow; }
            else if (a2f.IsSpeaking)     { statusStr = "▶ Speaking";                              statusColor = Color.green; }
            else                         { statusStr = "✔ Ready";                                 statusColor = new Color(0.5f, 1f, 0.5f); }

            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("■ Audio2Face-3D Neural Lip Sync テスト", EditorStyles.boldLabel, GUILayout.Width(310));
                var sc = new GUIStyle(EditorStyles.miniLabel) { normal = { textColor = statusColor } };
                EditorGUILayout.LabelField(statusStr, sc);
            }

            // VOICEVOX 設定行
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("VOICEVOX URL", GUILayout.Width(90));
                _voicevoxUrl = EditorGUILayout.TextField(_voicevoxUrl, GUILayout.Width(180));
                EditorGUILayout.LabelField("Spk", GUILayout.Width(26));
                _speakerId   = EditorGUILayout.IntField(_speakerId, GUILayout.Width(40));
            }

            // テキスト入力 + TTS+A2F 再生ボタン（音声あり）
            using (new EditorGUILayout.HorizontalScope())
            {
                _ttsText = EditorGUILayout.TextField(_ttsText, GUILayout.ExpandWidth(true));
                bool canPlay = Application.isPlaying && !_ttsRunning;
                GUI.enabled = canPlay;
                if (GUILayout.Button(_ttsRunning ? "合成中..." : "▶ TTS + A2F", GUILayout.Width(88), GUILayout.Height(22)))
                {
                    _useA2f = true;
                    RunTTS(_ttsText);
                }
                GUI.enabled = true;
            }

            // プリセット
            using (new EditorGUILayout.HorizontalScope())
            {
                foreach (var p in new[] { "こんにちは！", "ありがとう", "おはようございます", "おやすみなさい" })
                {
                    if (GUILayout.Button(p))
                    {
                        _ttsText = p;
                        if (Application.isPlaying && !_ttsRunning) { _useA2f = true; RunTTS(p); }
                    }
                }
            }

            // サイン波テスト（A2Fのみ、音声なし）
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("サイン波 (A2Fのみ)", EditorStyles.miniLabel, GUILayout.Width(130));
                GUI.enabled = Application.isPlaying && a2f != null && a2f.IsReady;
                if (GUILayout.Button("▶ 220Hz 4s", GUILayout.Width(90)))
                {
                    int sr  = 16000;
                    int n   = sr * 4;
                    var pcm = new float[n];
                    for (int i = 0; i < n; i++)
                        pcm[i] = Mathf.Sin(2f * Mathf.PI * 220f * i / sr) * 0.8f;
                    a2f.ProcessAudio(pcm);
                    SetStatus("▶ A2F: サイン波テスト送信 (4s)", Color.cyan);
                }
                if (GUILayout.Button("■ 停止", GUILayout.Width(60)))
                {
                    a2f?.StopSpeaking();
                    SetStatus("■ A2F: 停止", Color.gray);
                }
                GUI.enabled = true;
            }

            // ストリーミングテスト（TTS音声をチャンク分割して送信）
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("ストリーミングテスト", EditorStyles.miniLabel, GUILayout.Width(130));
                bool canStream = Application.isPlaying && !_ttsRunning;
                GUI.enabled = canStream;
                if (GUILayout.Button(_ttsRunning ? "合成中..." : "▶ TTS チャンク送信", GUILayout.Width(130), GUILayout.Height(22)))
                    RunTTSStreaming(_ttsText);
                GUI.enabled = true;
            }

            if (!Application.isPlaying)
                EditorGUILayout.HelpBox("Play Mode で起動すると動作します。", MessageType.Info);

            EditorGUILayout.Space(6);
        }

        // ── TTS + Lip Sync テスト ───────────────────────────────
        private void DrawTTSSection()
        {
            EditorGUILayout.LabelField("TTS + Lip Sync テスト (VOICEVOX)", EditorStyles.boldLabel);

            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("URL", GUILayout.Width(28));
                _voicevoxUrl = EditorGUILayout.TextField(_voicevoxUrl, GUILayout.Width(200));
                EditorGUILayout.LabelField("Speaker", GUILayout.Width(52));
                _speakerId   = EditorGUILayout.IntField(_speakerId, GUILayout.Width(44));
            }
            _useA2f = EditorGUILayout.Toggle("A2F も同時に使用 (Audio2Face-3D)", _useA2f);

            using (new EditorGUILayout.HorizontalScope())
            {
                _ttsText = EditorGUILayout.TextField(_ttsText, GUILayout.ExpandWidth(true));
                bool canPlay = Application.isPlaying && !_ttsRunning;
                GUI.enabled = canPlay;
                if (GUILayout.Button(_ttsRunning ? "..." : "▶ 再生", GUILayout.Width(64)))
                    RunTTS(_ttsText);
                GUI.enabled = true;
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                foreach (var preset in new[]
                    { "あいうえお", "こんにちは！", "ありがとうございます", "すごいですね", "おやすみなさい" })
                {
                    if (GUILayout.Button(preset, GUILayout.Width(118)))
                    {
                        _ttsText = preset;
                        if (Application.isPlaying && !_ttsRunning) RunTTS(preset);
                    }
                }
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("音素:", GUILayout.Width(32));
                foreach (var v in new[] { "a", "i", "u", "e", "o", "m", "fv" })
                {
                    string kana = VowelToText.TryGetValue(v, out var k) ? k : v;
                    if (GUILayout.Button($"{v}\n({kana})", GUILayout.Width(46), GUILayout.Height(36)))
                    {
                        if (Application.isPlaying && !_ttsRunning && kana.Length > 0)
                            RunTTS(kana);
                        else
                            SendVisemeDirect(v);
                    }
                }
                if (GUILayout.Button("sil", GUILayout.Width(40), GUILayout.Height(36)))
                    SendVisemeDirect("sil");
            }

            if (!Application.isPlaying)
                EditorGUILayout.HelpBox("Play Mode を起動すると実際の音声が再生されます。", MessageType.Info);
            EditorGUILayout.Space(6);
        }

        // ── Lip sync デモ (ブレンドシェイプのみ、音声なし) ───────────
        private void DrawLipSyncSection()
        {
            EditorGUILayout.LabelField("Lip Sync Demo (形状のみ、音声なし)", EditorStyles.boldLabel);
            EditorGUILayout.BeginHorizontal();
            if (!_lipSyncRunning)
            {
                if (GUILayout.Button("▶ Demo あいうえお (形状のみ)", GUILayout.Width(210)))
                    StartLipSyncDemo();
            }
            else
            {
                if (GUILayout.Button("■ Stop", GUILayout.Width(100)))
                    StopLipSync();
                EditorGUILayout.LabelField(
                    $"Playing… step {_lipSyncStep}/{LipSyncDemo.Length}",
                    GUILayout.ExpandWidth(true));
            }
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.Space(6);
        }

        // ── Reset ──────────────────────────────────────────────────────
        private void DrawResetSection()
        {
            EditorGUILayout.LabelField("Reset", EditorStyles.boldLabel);
            if (GUILayout.Button("Reset All (neutral / none / camera)", GUILayout.Height(28)))
                SendReset();
            EditorGUILayout.Space(4);
        }

        // ── AvatarController 取得 ──────────────────────────────────────
        private static AvatarController FindController()
        {
            if (!Application.isPlaying)
            {
                SetStatusStatic("⚠ Play Mode を起動してください", Color.yellow);
                return null;
            }
            var ctrl = UnityEngine.Object.FindFirstObjectByType<AvatarController>();
            if (ctrl == null)
                SetStatusStatic("⚠ AvatarController がシーンに見つかりません", Color.red);
            return ctrl;
        }

        // ── コマンド送信 ───────────────────────────────────────────────
        private void SendGesture(string gesture)
        {
            var ctrl = FindController();
            if (ctrl == null) return;
            Invoke(ctrl, "ApplyGesture", gesture);
            SetStatus($"▶ gesture={gesture}", Color.cyan);
        }

        private void SendEmotion(string emotion)
        {
            var ctrl = FindController();
            if (ctrl == null) return;
            Invoke(ctrl, "ApplyEmotion", emotion);
            SetStatus($"😀 emotion={emotion}", Color.green);
        }

        private void SendLookTarget(string target)
        {
            var ctrl = FindController();
            if (ctrl == null) return;
            Invoke(ctrl, "ApplyLookTarget", target);
            SetStatus($"👁 look={target}", Color.white);
        }

        private void SendVisemeDirect(string v)
        {
            var ctrl = FindController();
            if (ctrl == null) return;
            var method = typeof(AvatarController).GetMethod(
                "ApplyVisemeBlendShapes",
                BindingFlags.NonPublic | BindingFlags.Instance);
            method?.Invoke(ctrl, new object[] { v, 1.0f });
            SetStatus($"🎤 viseme={v}", Color.magenta);
        }

        // ── TTS 実行 ─────────────────────────────────────────────────
        private async void RunTTS(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return;
            var ctrl = FindController();
            if (ctrl == null) return;

            _ttsRunning = true;
            SetStatus($"⏳ VOICEVOX 合成中: {text}", Color.yellow);

            try
            {
                // HTTP は背景スレッドで実行 → メインスレッド(Update/OnGUI)をブロックしない
                string queryJson = null;
                byte[] wavBytes  = null;
                var url          = _voicevoxUrl;
                var spk          = _speakerId;

                await System.Threading.Tasks.Task.Run(async () =>
                {
                    using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };

                    // 1. audio_query
                    var qResp = await client.PostAsync(
                        $"{url}/audio_query?speaker={spk}&text={Uri.EscapeDataString(text)}", null);
                    if (!qResp.IsSuccessStatusCode)
                        throw new Exception($"audio_query 失敗: {qResp.StatusCode}");
                    queryJson = await qResp.Content.ReadAsStringAsync();

                    // 2. synthesis
                    var sResp = await client.PostAsync(
                        $"{url}/synthesis?speaker={spk}",
                        new StringContent(queryJson, Encoding.UTF8, "application/json"));
                    if (!sResp.IsSuccessStatusCode)
                        throw new Exception($"synthesis 失敗: {sResp.StatusCode}");
                    wavBytes = await sResp.Content.ReadAsByteArrayAsync();
                });

                // ── ここからメインスレッドに戻っている ──

                // 3. WAV → AudioClip
                var clip = WavToAudioClip(wavBytes, "tts_debug");
                if (clip == null) { SetStatus("❌ WAV 解析失敗", Color.red); return; }

                // 4. 音素タイムライン構築
                var events = ParseMorasToVisemeEvents(queryJson);

                // 5. AudioSource 準備
                var src = ctrl.gameObject.GetComponent<AudioSource>();
                if (src == null)
                {
                    Debug.LogWarning("[AvatarDebug] AudioSource not found — adding.");
                    src = ctrl.gameObject.AddComponent<AudioSource>();
                }
                src.spatialBlend = 0f;
                src.clip = clip;

                // 6. Play と HandleViseme を同一フレームで呼ぶ
                //    → _visemeStartTime = Time.time が src.Play() と同期する
                src.Play();
                SendVisemeTimeline(ctrl, events);

                // 7. A2F neural lip sync: WAV PCM を Audio2Face-3D に渡す
                bool a2fActive = false;
                if (_useA2f)
                {
                    var a2f = UnityEngine.Object.FindFirstObjectByType<Audio2FaceLipSync>();
                    if (a2f != null && a2f.IsReady)
                    {
                        var pcm24k = WavToFloat32(wavBytes);
                        var pcm16k = ResampleLinear(pcm24k, 24000, 16000);
                        a2f.ProcessAudio(pcm16k);
                        a2fActive = true;
                    }
                    else
                    {
                        Debug.LogWarning("[AvatarDebug] A2F: Audio2FaceLipSync not ready (Editor limitation — TRT unavailable).");
                    }
                }

                // 8. A2G upper-body gesture: WAV PCM を Audio2GestureController に渡す
                //    A2G は Editor でも動作するため、TTS テスト時に上半身ジェスチャーを確認できる。
                bool a2gActive = false;
                {
                    var a2g = UnityEngine.Object.FindFirstObjectByType<Audio2GestureController>();
                    if (a2g != null && a2g.IsReady)
                    {
                        var pcm24k = WavToFloat32(wavBytes);
                        var pcm16k = ResampleLinear(pcm24k, 24000, 16000);
                        a2g.PushAudioChunk(pcm16k, isFirst: true);
                        a2g.CloseStream();
                        a2gActive = true;
                        Debug.Log($"[AvatarDebug] A2G: sent {pcm16k.Length} samples to Audio2GestureController.");
                    }
                    else
                    {
                        Debug.LogWarning("[AvatarDebug] A2G: Audio2GestureController not ready.");
                    }
                }

                string suffix = (a2fActive, a2gActive) switch
                {
                    (true,  true)  => "TTS+A2F+A2G",
                    (false, true)  => "TTS+A2G (A2F未準備)",
                    (true,  false) => "TTS+A2F",
                    _              => "音声のみ",
                };
                SetStatus($"▶ 再生中 ({suffix}): {text}  ({clip.length:F1}s)",
                          a2gActive ? new Color(0.2f, 1f, 0.5f) : new Color(1f, 0.8f, 0.2f));
            }
            catch (Exception ex)
            {
                SetStatus($"❌ {ex.GetType().Name}: {ex.Message}", Color.red);
                Debug.LogException(ex);
            }
            finally
            {
                _ttsRunning = false;
                Repaint();
            }
        }

        // ── ストリーミング A2F テスト: TTS 音声をチャンク分割して PushAudioChunk に渡す ──
        // 実際の main.py と同じコードパス (PushAudioChunk + CloseStream) を Editor から検証できる。
        private async void RunTTSStreaming(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return;
            var ctrl = FindController();
            if (ctrl == null) return;

            _ttsRunning = true;
            SetStatus($"⏳ VOICEVOX 合成中 (ストリーミング): {text}", Color.yellow);

            try
            {
                string queryJson = null;
                byte[] wavBytes  = null;
                var url          = _voicevoxUrl;
                var spk          = _speakerId;

                await System.Threading.Tasks.Task.Run(async () =>
                {
                    using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                    var qResp = await client.PostAsync(
                        $"{url}/audio_query?speaker={spk}&text={Uri.EscapeDataString(text)}", null);
                    if (!qResp.IsSuccessStatusCode)
                        throw new Exception($"audio_query 失敗: {qResp.StatusCode}");
                    queryJson = await qResp.Content.ReadAsStringAsync();

                    var sResp = await client.PostAsync(
                        $"{url}/synthesis?speaker={spk}",
                        new StringContent(queryJson, Encoding.UTF8, "application/json"));
                    if (!sResp.IsSuccessStatusCode)
                        throw new Exception($"synthesis 失敗: {sResp.StatusCode}");
                    wavBytes = await sResp.Content.ReadAsByteArrayAsync();
                });

                var clip = WavToAudioClip(wavBytes, "tts_stream_debug");
                if (clip == null) { SetStatus("❌ WAV 解析失敗", Color.red); return; }

                // 音素タイムライン構築 (RunTTS と同様に viseme も送る)
                var events = ParseMorasToVisemeEvents(queryJson);

                // AudioSource 再生
                var src = ctrl.gameObject.GetComponent<AudioSource>();
                if (src == null) src = ctrl.gameObject.AddComponent<AudioSource>();
                src.spatialBlend = 0f;
                src.clip = clip;
                src.Play();

                // Play と同時に viseme タイムラインを開始 (TtsViseme / Hybrid モードで口を動かす)
                SendVisemeTimeline(ctrl, events);

                // A2F ストリーミング: 8192 サンプルずつチャンク送信
                var a2fStream = UnityEngine.Object.FindFirstObjectByType<Audio2FaceLipSync>();
                if (a2fStream != null && a2fStream.IsReady)
                {
                    const int chunkSamples = 8192;
                    var pcm24k = WavToFloat32(wavBytes);
                    var pcm16k = ResampleLinear(pcm24k, 24000, 16000);
                    bool isFirst = true;
                    for (int i = 0; i < pcm16k.Length; i += chunkSamples)
                    {
                        int len   = Mathf.Min(chunkSamples, pcm16k.Length - i);
                        var chunk = new float[len];
                        System.Array.Copy(pcm16k, i, chunk, 0, len);
                        a2fStream.PushAudioChunk(chunk, isFirst);
                        isFirst = false;
                    }
                    a2fStream.CloseStream();
                    SetStatus($"▶ ストリーミング A2F 再生中: {text}  ({clip.length:F1}s, {pcm16k.Length / chunkSamples + 1} chunks)",
                              new Color(0.2f, 1f, 0.8f));
                }
                else
                {
                    Debug.LogWarning("[AvatarDebug] Streaming A2F: Audio2FaceLipSync not ready.");
                    SetStatus($"▶ 再生中 (A2F未準備): {text}  ({clip.length:F1}s)",
                              new Color(1f, 0.8f, 0.2f));
                }
            }
            catch (Exception ex)
            {
                SetStatus($"❌ {ex.GetType().Name}: {ex.Message}", Color.red);
                Debug.LogException(ex);
            }
            finally
            {
                _ttsRunning = false;
                Repaint();
            }
        }

        // ── VOICEVOX audio_query JSON → VisemeEvent リスト ───────────
        // accent_phrases[].moras[].{vowel, consonant_length, vowel_length} を累積して t_ms を計算。
        private static List<(int t_ms, string v)> ParseMorasToVisemeEvents(string json)
        {
            var result = new List<(int, string)> { (0, "sil") };
            float tSec = 0f;

            // pre_phoneme_length を取得して先頭の無音時間を加算
            var prePhonemeMatch = System.Text.RegularExpressions.Regex.Match(
                json, @"""pre_phoneme_length""\s*:\s*(?<v>[\d.]+)");
            if (prePhonemeMatch.Success)
                tSec += float.Parse(prePhonemeMatch.Groups["v"].Value,
                                    System.Globalization.CultureInfo.InvariantCulture);

            // mora ブロックを抽出。末尾の """ を取り除き数値後の " を要求しないよう修正。
            // VOICEVOX mora JSON 例: {"consonant_length": null, "vowel": "a", "vowel_length": 0.152}
            var moraPattern = new System.Text.RegularExpressions.Regex(
                @"""consonant_length""\s*:\s*(?<c>[\d.]+|null).*?""vowel""\s*:\s*""(?<v>[^""]+)"".*?""vowel_length""\s*:\s*(?<vl>[\d.]+)",
                System.Text.RegularExpressions.RegexOptions.Singleline);
            int matchCount = 0;
            foreach (System.Text.RegularExpressions.Match m in moraPattern.Matches(json))
            {
                float c  = m.Groups["c"].Value == "null" ? 0f
                         : float.Parse(m.Groups["c"].Value,
                                       System.Globalization.CultureInfo.InvariantCulture);
                float vl = float.Parse(m.Groups["vl"].Value,
                                       System.Globalization.CultureInfo.InvariantCulture);
                string vowel = m.Groups["v"].Value;
                tSec += c;
                string vis = vowel switch
                {
                    "a" => "a", "i" => "i", "u" => "u", "e" => "e", "o" => "o",
                    "N" => "m",
                    "cl" => "sil",
                    _ => "sil",
                };
                result.Add(((int)(tSec * 1000f), vis));
                tSec += vl;
                matchCount++;
            }
            result.Add(((int)(tSec * 1000f), "sil"));
            Debug.Log($"[AvatarDebug] ParseMoras: {matchCount} moras, total={tSec * 1000f:F0}ms, events={result.Count}");
            return result;
        }

        // ── VisemeEvent リスト → LipSyncController.HandleViseme ─────
        private static void SendVisemeTimeline(AvatarController ctrl, List<(int t_ms, string v)> events)
        {
            var evArray = new VisemeEvent[events.Count];
            for (int i = 0; i < events.Count; i++)
                evArray[i] = new VisemeEvent { t_ms = events[i].t_ms, v = events[i].v };

            var p = new AvatarVisemeParams
            {
                events       = evArray,
                crossfade_ms = 60,
                strength     = 1.0f,
            };

            // LipSyncController.HandleViseme は public なので直接呼ぶ。
            // AvatarController に HandleViseme メソッドは存在しない（switch 内で委譲）。
            var lipSync = ctrl.GetComponent<LipSyncController>();
            if (lipSync != null)
            {
                lipSync.HandleViseme(p);
                Debug.Log($"[AvatarDebug] SendVisemeTimeline → LipSyncController ({evArray.Length} events)");
            }
            else
            {
                Debug.LogWarning("[AvatarDebug] LipSyncController not found on AvatarController's GameObject.");
            }
        }

        // ── WAV バイト列 → AudioClip ─────────────────────────────────
        // WAV ヘッダー解析 + PCM16 → float 変換
        private static AudioClip WavToAudioClip(byte[] wav, string clipName)
        {
            try
            {
                // ヘッダー解析
                int channels   = BitConverter.ToInt16(wav, 22);
                int sampleRate = BitConverter.ToInt32(wav, 24);
                int bitDepth   = BitConverter.ToInt16(wav, 34);

                // "data" チャンクを探す
                int dataStart = 12;
                while (dataStart < wav.Length - 8)
                {
                    string chunkId = Encoding.ASCII.GetString(wav, dataStart, 4);
                    int    chunkSz = BitConverter.ToInt32(wav, dataStart + 4);
                    dataStart += 8;
                    if (chunkId == "data") break;
                    dataStart += chunkSz;
                }

                int bytesPerSample = bitDepth / 8;
                int sampleCount    = (wav.Length - dataStart) / bytesPerSample;
                var samples        = new float[sampleCount];

                float scale = bitDepth == 16 ? 32768f : 128f;
                for (int i = 0; i < sampleCount; i++)
                {
                    int offset = dataStart + i * bytesPerSample;
                    samples[i] = bitDepth == 16
                        ? BitConverter.ToInt16(wav, offset) / scale
                        : (wav[offset] - 128) / scale;
                }

                var clip = AudioClip.Create(clipName, sampleCount / channels,
                                            channels, sampleRate, false);
                clip.SetData(samples, 0);
                return clip;
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[AvatarDebug] WavToAudioClip failed: {ex.Message}");
                return null;
            }
        }

        // ── A2F ヘルパー (WAV→float32, リサンプル) ─────────────────────────

        private static float[] WavToFloat32(byte[] wav)
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

        private void SendAvatarEvent(string eventName, float intensity)
        {
            var ctrl = FindController();
            if (ctrl == null) return;

            var p = new AvatarEventParams { @event = eventName, intensity = intensity };
            var method = typeof(AvatarController).GetMethod(
                "HandleEvent",
                BindingFlags.NonPublic | BindingFlags.Instance);
            method?.Invoke(ctrl, new object[] { p });
        }

        private void SendReset()
        {
            var ctrl = FindController();
            if (ctrl == null) return;
            Invoke(ctrl, "ApplyEmotion", "neutral");
            Invoke(ctrl, "ApplyGesture", "none");
            Invoke(ctrl, "ApplyLookTarget", "camera");
            _commentScanActive = false;
            SetStatus("🔄 Reset", Color.gray);
        }

        // ── Lip sync デモ (EditorApplication.update で tick) ──────────
        private void StartLipSyncDemo()
        {
            if (FindController() == null) return;
            _lipSyncRunning = true;
            _lipSyncStep    = 0;
            _lipSyncStartTime = EditorApplication.timeSinceStartup * 1000.0;
            SetStatus("🎤 Lip sync demo…", Color.magenta);
        }

        private void StopLipSync()
        {
            _lipSyncRunning = false;
            SendVisemeDirect("sil");
            SetStatus("■ Lip sync stopped", Color.gray);
        }

        private void TickLipSync()
        {
            if (!_lipSyncRunning) return;
            double elapsed = EditorApplication.timeSinceStartup * 1000.0 - _lipSyncStartTime;

            while (_lipSyncStep < LipSyncDemo.Length
                   && elapsed >= LipSyncDemo[_lipSyncStep].dt)
            {
                SendVisemeDirect(LipSyncDemo[_lipSyncStep].v);
                _lipSyncStep++;
            }

            if (_lipSyncStep >= LipSyncDemo.Length)
            {
                _lipSyncRunning = false;
                SetStatus("✅ Lip sync demo 完了", new Color(0.2f, 0.9f, 0.4f));
            }
        }

        // ── Reflection ヘルパー ────────────────────────────────────────
        private static void Invoke(AvatarController ctrl, string methodName, string arg)
        {
            var method = typeof(AvatarController).GetMethod(
                methodName,
                BindingFlags.NonPublic | BindingFlags.Instance,
                null,
                new[] { typeof(string) },
                null);
            if (method == null)
            {
                Debug.LogWarning($"[AvatarDebug] Method not found: {methodName}");
                return;
            }
            method.Invoke(ctrl, new object[] { arg });
        }

        // ── ステータス ────────────────────────────────────────────────
        private void SetStatus(string msg, Color c)
        {
            _status = msg;
            _statusColor = c;
            Repaint();
        }

        // static 版 (Play Mode チェック等で使用)
        private static AvatarDebugWindow _instance;
        private static void SetStatusStatic(string msg, Color c)
        {
            _instance = GetWindow<AvatarDebugWindow>("Avatar Debug");
            _instance._status = msg;
            _instance._statusColor = c;
        }

        private void OnEnable()  => _instance = this;
        private void OnDisable() { _instance = null; }
    }
}

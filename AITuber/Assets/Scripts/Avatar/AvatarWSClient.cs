// AvatarWSClient.cs
// Thin WebSocket client connecting to the Orchestrator.
// SRS refs: FR-A7-01, protocols/avatar_ws.yml
//
// Hard rules (from unity-avatar-client.agent.md):
// - No business logic: no chat parsing, no Bandit, no LLM calls.
// - Validate JSON, ignore unknown fields, never crash on unknown commands.
// - Keep Update loop light; avoid allocations.

using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// WebSocket client that listens for avatar commands from the Python Orchestrator.
    /// Endpoint default: ws://127.0.0.1:31900
    /// </summary>
    public class AvatarWSClient : MonoBehaviour
    {
        [Header("Connection")]
        [SerializeField] private string _host = "127.0.0.1";
        [SerializeField] private int _port = 31900;
        [SerializeField] private float _reconnectIntervalSec = 3f;

        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private readonly ConcurrentQueue<string> _incomingQueue = new();
        private bool _connected;
        private SynchronizationContext _mainThread;

        /// <summary>Raised on the main thread when a valid message arrives.</summary>
        public event Action<AvatarMessage, object> OnMessageReceived;

        // ── Lifecycle ────────────────────────────────────────────────

        private void OnEnable()
        {
            // メインスレッドのSyncContextを取得（必ずOnEnableで取得してキャプチャ）
            _mainThread = SynchronizationContext.Current;
            Debug.Log($"[AvatarWS] OnEnable: starting ws://{_host}:{_port} (syncCtx={_mainThread != null})");
            _cts = new CancellationTokenSource();
            _ = ConnectLoop(_cts.Token);
        }

        private void OnDisable()
        {
            _cts?.Cancel();
            _cts?.Dispose();
            _cts = null;
            CloseSocket();
        }

        private void Update()
        {
            // Drain incoming queue on the main thread (allocation-free iteration).
            // Also handled via SynchronizationContext as fallback.
            while (_incomingQueue.TryDequeue(out string json))
            {
                TryDispatch(json);
            }
        }

        // ── Connection loop ──────────────────────────────────────────

        private async Task ConnectLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    _ws = new ClientWebSocket();
                    var uri = new Uri($"ws://{_host}:{_port}");
                    await _ws.ConnectAsync(uri, ct);
                    _connected = true;
                    Debug.Log($"[AvatarWS] Connected to {uri}");
                    await ReceiveLoop(ct);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[AvatarWS] Connection failed: {ex.Message}");
                }
                finally
                {
                    _connected = false;
                    CloseSocket();
                }

                // Wait before reconnecting
                try
                {
                    await Task.Delay(
                        TimeSpan.FromSeconds(_reconnectIntervalSec), ct);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
            }
        }

        private async Task ReceiveLoop(CancellationToken ct)
        {
            var buffer = new byte[4096];
            var sb = new StringBuilder();

            while (_ws.State == WebSocketState.Open && !ct.IsCancellationRequested)
            {
                WebSocketReceiveResult result;
                try
                {
                    result = await _ws.ReceiveAsync(
                        new ArraySegment<byte>(buffer), ct);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (WebSocketException ex)
                {
                    Debug.LogWarning($"[AvatarWS] Receive error: {ex.Message}");
                    break;
                }

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("[AvatarWS] Server closed connection.");
                    break;
                }

                sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));

                if (result.EndOfMessage)
                {
                    var msgStr = sb.ToString();
                    sb.Clear();
                    // SynchronizationContext 経由でメインスレッドに dispatch（Update依存を廃止）
                    if (_mainThread != null)
                    {
                        _mainThread.Post(_ => TryDispatch(msgStr), null);
                    }
                    else
                    {
                        // フォールバック: Updateで処理するキューに積む
                        _incomingQueue.Enqueue(msgStr);
                    }
                }
            }
        }

        // ── Dispatch ─────────────────────────────────────────────────

        private void TryDispatch(string json)
        {
            var (msg, typedParams) = AvatarMessageParser.Parse(json);

            if (msg == null)
            {
                Debug.LogWarning("[AvatarWS] Invalid JSON received.");
                return;
            }

            // Backward compatible: unknown commands logged but not crashed.
            OnMessageReceived?.Invoke(msg, typedParams);
        }

        // ── Cleanup ──────────────────────────────────────────────────

        private void CloseSocket()
        {
            try
            {
                if (_ws != null && _ws.State == WebSocketState.Open)
                {
                    _ws.CloseAsync(
                        WebSocketCloseStatus.NormalClosure,
                        "Client shutdown",
                        CancellationToken.None).Wait(2000);
                }
            }
            catch
            {
                // Best-effort close
            }
            _ws?.Dispose();
            _ws = null;
        }

        public bool IsConnected => _connected;

        /// <summary>
        /// Send a raw JSON string to the Orchestrator over the WebSocket.
        /// FR-E4-01: Used by PerceptionReporter to push perception_update messages.
        /// No-ops when not connected.
        /// </summary>
        public async Task SendJsonAsync(string json)
        {
            if (_ws == null || _ws.State != WebSocketState.Open) return;
            try
            {
                var bytes = Encoding.UTF8.GetBytes(json);
                await _ws.SendAsync(
                    new ArraySegment<byte>(bytes),
                    WebSocketMessageType.Text,
                    true,
                    _cts?.Token ?? CancellationToken.None);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[AvatarWS] SendJsonAsync failed: {ex.Message}");
            }
        }
    }
}

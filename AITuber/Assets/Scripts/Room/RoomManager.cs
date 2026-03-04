// RoomManager.cs
// 部屋（Room Prefab）の切り替えを管理する MonoBehaviour。
// SRS ref: FR-ROOM-01, FR-ROOM-02
//
// 設置方法:
//   1. SampleScene に空の GameObject "RoomManager" を作り Attach。
//   2. Inspector で Rooms[] に RoomDefinition ScriptableObject をアサイン。
//   3. AvatarRoot にアバター(U.fbx)の root Transform をアサイン。
//   4. Main Camera をアサイン。
//
// Orchestrator 連携:
//   `{ "cmd": "room_change", "params": { "room_id": "alchemist" } }` を WS で送ると
//   AvatarController 経由で SwitchRoom("alchemist") が呼ばれる。
//
// キーボードショートカット（デバッグ時）:
//   [ / ] で前後の部屋に切り替え。

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace AITuber.Room
{
    public class RoomManager : MonoBehaviour
    {
        // ── Inspector ────────────────────────────────────────────────

        [Header("部屋定義リスト（上から順に 0, 1, 2... ）")]
        [SerializeField] private RoomDefinition[] _rooms = Array.Empty<RoomDefinition>();

        [Header("参照")]
        [SerializeField] private Transform  _avatarRoot;
        [SerializeField] private Camera     _mainCamera;

        [Header("フェードオブジェクト（任意）")]
        [Tooltip("FadeCanvas など。なければスムーズ移動のみ")]
        [SerializeField] private CanvasGroup _fadeCanvas;

        // ── State ────────────────────────────────────────────────────

        private readonly Dictionary<string, (RoomDefinition def, GameObject instance)> _roomMap = new();
        private int    _currentIndex = -1;
        private bool   _transitioning;

        // ── Singleton helper ─────────────────────────────────────────

        public static RoomManager Instance { get; private set; }

        /// <summary>テスト用: シングルトン参照をクリアする。本番コードからは呼ばない。</summary>
        public static void ClearInstanceForTest() => Instance = null;

        // ── Unity ────────────────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
        }

        private void Start()
        {
            // 全部屋を非アクティブで Instantiate しておく
            foreach (var def in _rooms)
            {
                if (def == null || string.IsNullOrEmpty(def.roomId))
                {
                    Debug.LogWarning("[RoomManager] null or missing roomId — skipped");
                    continue;
                }
                if (_roomMap.ContainsKey(def.roomId))
                {
                    Debug.LogWarning($"[RoomManager] Duplicate roomId '{def.roomId}' — skipped");
                    continue;
                }

                GameObject instance = null;
                if (def.roomPrefab != null)
                {
                    instance = Instantiate(def.roomPrefab, Vector3.zero, Quaternion.identity);
                    instance.name = $"Room_{def.roomId}";
                    instance.SetActive(false);
                }
                else
                {
                    Debug.LogWarning($"[RoomManager] Room '{def.roomId}' has no prefab assigned.");
                }

                _roomMap[def.roomId] = (def, instance);
            }

            // 最初の部屋を有効化
            if (_rooms.Length > 0 && _rooms[0] != null)
                SwitchRoom(_rooms[0].roomId);
        }

        private void Update()
        {
            // デバッグ用キー切り替え
            if (Input.GetKeyDown(KeyCode.LeftBracket))  PrevRoom();
            if (Input.GetKeyDown(KeyCode.RightBracket)) NextRoom();
        }

        // ── Public API ───────────────────────────────────────────────

        /// <summary>roomId を指定して部屋切り替え。</summary>
        public void SwitchRoom(string roomId)
        {
            if (_transitioning) return;
            if (string.IsNullOrEmpty(roomId))
            {
                Debug.LogWarning("[RoomManager] SwitchRoom called with empty roomId");
                return;
            }
            if (!_roomMap.TryGetValue(roomId, out var entry))
            {
                Debug.LogWarning($"[RoomManager] Room '{roomId}' not found.");
                return;
            }

            int newIndex = Array.FindIndex(_rooms, r => r != null && r.roomId == roomId);
            if (newIndex == _currentIndex) return;

            StartCoroutine(DoSwitch(newIndex, entry.def, entry.instance));
        }

        /// <summary>インデックス指定。</summary>
        public void SwitchRoom(int index)
        {
            if (index < 0 || index >= _rooms.Length || _rooms[index] == null) return;
            SwitchRoom(_rooms[index].roomId);
        }

        public void NextRoom() => SwitchRoom((_currentIndex + 1) % _rooms.Length);
        public void PrevRoom() => SwitchRoom((_currentIndex - 1 + _rooms.Length) % _rooms.Length);

        /// <summary>現在の部屋 ID（UI表示などに）。</summary>
        public string CurrentRoomId => _currentIndex >= 0 && _rooms[_currentIndex] != null
            ? _rooms[_currentIndex].roomId
            : string.Empty;

        // ── Switch Coroutine ─────────────────────────────────────────

        private IEnumerator DoSwitch(int newIndex, RoomDefinition def, GameObject newInstance)
        {
            _transitioning = true;

            // ── フェードアウト ──────────────────────────────
            if (_fadeCanvas != null && def.useFadeTransition)
                yield return StartCoroutine(Fade(0f, 1f, def.transitionDuration / 2f));

            // ── 旧部屋を非表示 ─────────────────────────────
            if (_currentIndex >= 0 && _rooms[_currentIndex] != null)
            {
                var oldId = _rooms[_currentIndex].roomId;
                if (_roomMap.TryGetValue(oldId, out var old) && old.instance != null)
                    old.instance.SetActive(false);
            }

            // ── 新部屋を表示 ───────────────────────────────
            if (newInstance != null)
                newInstance.SetActive(true);

            _currentIndex = newIndex;

            // ── カメラ移動 ─────────────────────────────────
            if (_mainCamera != null)
            {
                _mainCamera.transform.position    = def.cameraPosition;
                _mainCamera.transform.eulerAngles = def.cameraEuler;
                _mainCamera.fieldOfView           = def.cameraFov;
            }

            // ── アバター移動 ───────────────────────────────
            if (_avatarRoot != null)
            {
                _avatarRoot.position    = def.avatarPosition;
                _avatarRoot.eulerAngles = def.avatarEuler;
            }

            // ── 床スナップ（AvatarGrounding コンポーネントがあれば）──
            // Animator の LateUpdate 完了後に足ボーン位置を計測して正確にスナップ
            if (_avatarRoot != null)
            {
                var grounding = _avatarRoot.GetComponent<AITuber.Avatar.AvatarGrounding>();
                if (grounding != null)
                    yield return StartCoroutine(grounding.SnapCoroutine());
            }

            // ── フェードイン ───────────────────────────────
            if (_fadeCanvas != null && def.useFadeTransition)
                yield return StartCoroutine(Fade(1f, 0f, def.transitionDuration / 2f));

            _transitioning = false;
            Debug.Log($"[RoomManager] Switched to '{def.roomId}' ({def.displayName})");
        }

        // ── Fade helper ──────────────────────────────────────────────

        private IEnumerator Fade(float from, float to, float duration)
        {
            if (_fadeCanvas == null) yield break;
            _fadeCanvas.gameObject.SetActive(true);
            float t = 0f;
            while (t < duration)
            {
                t += Time.deltaTime;
                _fadeCanvas.alpha = Mathf.Lerp(from, to, t / duration);
                yield return null;
            }
            _fadeCanvas.alpha = to;
            if (to <= 0f) _fadeCanvas.gameObject.SetActive(false);
        }

        // ── Editor Gizmo ─────────────────────────────────────────────
#if UNITY_EDITOR
        private void OnGUI()
        {
            if (!Application.isPlaying) return;
            var style = new GUIStyle(GUI.skin.box) { fontSize = 11 };
            GUI.Box(new Rect(10, Screen.height - 50, 220, 38),
                $"Room: {CurrentRoomId}  ([/] to cycle)", style);
        }
#endif
    }
}

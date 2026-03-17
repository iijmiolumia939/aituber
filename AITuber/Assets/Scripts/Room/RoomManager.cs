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
using UnityEngine.AI;

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

        [Header("アバター配置補正")]
        [Tooltip("room definition の avatarPosition 近傍から NavMesh 上の開始点を検索する半径")]
        [SerializeField] private float _avatarSpawnNavMeshRadius = 3.0f;

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

        private void OnDisable()
        {
            Debug.LogWarning($"[RoomManager] OnDisable! isActiveAndEnabled={isActiveAndEnabled} gameObject.activeSelf={gameObject.activeSelf}");
        }

        private void OnDestroy()
        {
            Debug.LogWarning("[RoomManager] OnDestroy! Coroutines will stop.");
            if (Instance == this) Instance = null;
        }

        private void Start()
        {
            // 全部屋を非アクティブで準備する。
            // ── 優先順位 ──────────────────────────────────────────────
            // 1. シーン上に既存の "Room_{roomId}" GO があれば再利用（Edit Mode 事前配置対応）
            // 2. なければ def.roomPrefab を Instantiate する（フォールバック）
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

                // シーン上の既存インスタンスを探す（非アクティブも含む）
                // GameObject.Find は非アクティブ GO を見つけられないため GetRootGameObjects を使用
                var expectedName = $"Room_{def.roomId}";
                GameObject instance = null;
                foreach (var root in gameObject.scene.GetRootGameObjects())
                {
                    if (root.name == expectedName) { instance = root; break; }
                }

                if (instance != null)
                {
                    // Edit Mode で事前配置されていた場合はそのまま流用
                    Debug.Log($"[RoomManager] Using pre-placed instance '{expectedName}'");
                }
                else if (def.roomPrefab != null)
                {
                    // 見つからなければ Instantiate（フォールバック）
                    instance = Instantiate(def.roomPrefab, Vector3.zero, Quaternion.identity);
                    instance.name = expectedName;
                    Debug.Log($"[RoomManager] Instantiated room '{expectedName}'");
                }
                else
                {
                    Debug.LogWarning($"[RoomManager] Room '{def.roomId}' has no prefab assigned.");
                }

                if (instance != null)
                    instance.SetActive(false);

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
                var resolvedSpawnPosition = ResolveAvatarSpawnPosition(def.avatarPosition, def.roomId);

                // #67: NavMeshAgent 一本化 — agent を無効化してからワープし、
                // BeginSnap で再度有効化する。
                var grounding = _avatarRoot.GetComponent<AITuber.Avatar.AvatarGrounding>();
                if (grounding != null)
                    grounding.DisableAgent();

                _avatarRoot.position    = resolvedSpawnPosition;
                _avatarRoot.eulerAngles = def.avatarEuler;
                Debug.Log(
                    $"[RoomManager] room='{def.roomId}': avatar spawn final={resolvedSpawnPosition} " +
                    $"desired={def.avatarPosition} euler={def.avatarEuler}");
            }

            // ── 床スナップ（AvatarGrounding コンポーネントがあれば）──
            // Animator の LateUpdate 完了後に足ボーン位置を計測して正確にスナップ
            if (_avatarRoot != null)
            {
                var grounding = _avatarRoot.GetComponent<AITuber.Avatar.AvatarGrounding>();
                if (grounding != null)
                    // BeginSnap は Update ステートマシンを開始する（コルーチン不使用）。
                    // #67: BeginSnap 完了時に NavMeshAgent を再有効化する。
                    grounding.BeginSnap();
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

        private Vector3 ResolveAvatarSpawnPosition(Vector3 desiredPosition, string roomId)
        {
            var sampleOrigin = desiredPosition + Vector3.up * 0.5f;
            if (!NavMesh.SamplePosition(sampleOrigin, out NavMeshHit hit, _avatarSpawnNavMeshRadius, NavMesh.AllAreas))
            {
                Debug.LogWarning(
                    $"[RoomManager] room='{roomId}': no NavMesh found near avatarPosition={desiredPosition} " +
                    $"(radius={_avatarSpawnNavMeshRadius:F1}m). Using definition position.");
                return desiredPosition;
            }

            float horizontalDrift = Vector2.Distance(
                new Vector2(desiredPosition.x, desiredPosition.z),
                new Vector2(hit.position.x, hit.position.z));

            if (horizontalDrift > 0.01f)
            {
                Debug.Log(
                    $"[RoomManager] room='{roomId}': avatar spawn projected to NavMesh. " +
                    $"desired={desiredPosition} navMesh={hit.position} drift={horizontalDrift:F2}m");
            }

            return hit.position;
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
